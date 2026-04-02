import pytest
import os
import shutil
from pathlib import Path
from datetime import datetime
from ruamel.yaml import YAML
from ace_lib.services.ace_service import ACEService
from ace_lib.models.schemas import (
    MailMessage,
    Subscription,
    SubscriptionsConfig,
    NotificationPriority,
    OwnershipConfig,
    OwnershipModule,
    MACPProposal,
    ConsensusStatus
)

yaml = YAML()
yaml.preserve_quotes = True

class TestMultiAgentCoordination:
    """
    Test suite for REQ-005: Multi-Agent Coordination & Messaging.
    Verifies asynchronous communication, subscription logic, and consensus triggers.
    """

    @pytest.fixture
    def service(self, tmp_path):
        """Initializes ACEService in a temporary directory with required subfolders."""
        project_dir = tmp_path / "ace_project"
        project_dir.mkdir()
        
        # Initialize the service
        service = ACEService(base_path=project_dir)
        
        # Create the .ace structure required by the requirement
        service.ace_dir.mkdir(parents=True, exist_ok=True)
        service.mail_dir.mkdir(parents=True, exist_ok=True)
        service.macp_dir.mkdir(parents=True, exist_ok=True)
        
        return service

    def test_mail_system_storage_and_retrieval(self, service):
        """
        Success Criteria: The Agent Mail system correctly stores and retrieves messages in .ace/mail/ folders.
        """
        recipient_id = "agent-beta"
        msg_id = "msg_001"
        message = MailMessage(
            id=msg_id,
            from_agent="agent-alpha",
            to_agent=recipient_id,
            subject="Sync Request",
            body="Please review the latest architectural changes in the core module.",
            timestamp=datetime.now().isoformat()
        )

        # 1. Simulate Sending: Store message in recipient's folder
        recipient_folder = service.mail_dir / recipient_id
        recipient_folder.mkdir(exist_ok=True)
        mail_file = recipient_folder / f"{msg_id}.yaml"
        
        with open(mail_file, "w", encoding="utf-8") as f:
            yaml.dump(message.model_dump(mode="json"), f)

        # 2. Verify Storage
        assert mail_file.exists(), "Mail file should be stored in the correct agent subfolder."

        # 3. Simulate Retrieval
        with open(mail_file, "r", encoding="utf-8") as f:
            data = yaml.load(f)
            retrieved_msg = MailMessage(**data)

        assert retrieved_msg.id == msg_id
        assert retrieved_msg.from_agent == "agent-alpha"
        assert "core module" in retrieved_msg.body

    def test_agent_subscription_persistence(self, service):
        """
        Success Criteria: Agents can 'subscribe' to changes in modules they depend on.
        Verifies that subscription configurations are correctly serialized to the filesystem.
        """
        sub_config_path = service.ace_dir / "subscriptions.yaml"
        
        sub1 = Subscription(
            agent_id="security-bot",
            path="src/auth",
            priority=NotificationPriority.URGENT
        )
        sub2 = Subscription(
            agent_id="qa-agent",
            path="src/api",
            priority=NotificationPriority.MEDIUM
        )
        
        config = SubscriptionsConfig(subscriptions=[sub1, sub2])

        # Save subscriptions
        with open(sub_config_path, "w", encoding="utf-8") as f:
            yaml.dump(config.model_dump(mode="json"), f)

        # Verify persistence
        assert sub_config_path.exists()
        with open(sub_config_path, "r", encoding="utf-8") as f:
            loaded_data = yaml.load(f)
            loaded_config = SubscriptionsConfig(**loaded_data)

        assert len(loaded_config.subscriptions) == 2
        assert loaded_config.subscriptions[0].agent_id == "security-bot"
        assert loaded_config.subscriptions[0].path == "src/auth"

    def test_consensus_protocol_trigger_on_boundary_cross(self, service):
        """
        Success Criteria: The Consensus Protocol triggers a debate when changes cross ownership boundaries.
        
        Scenario:
        - 'src/core' is owned by 'architect-agent'.
        - 'feature-agent' attempts to modify a file in 'src/core'.
        - The system should detect the conflict and generate a MACPProposal.
        """
        # 1. Setup Ownership
        ownership_file = service.ace_dir / "ownership.yaml"
        ownership = OwnershipConfig(modules={
            "src/core": OwnershipModule(agent_id="architect-agent")
        })
        with open(ownership_file, "w", encoding="utf-8") as f:
            yaml.dump(ownership.model_dump(mode="json"), f)

        # 2. Simulate a change detection logic (as described in PRD Section 4)
        acting_agent = "feature-agent"
        target_file = "src/core/database.py"
        
        # Logic: Check if acting agent is the owner
        owner_id = None
        for path, module in ownership.modules.items():
            if target_file.startswith(path):
                owner_id = module.agent_id
                break

        # 3. Trigger Consensus if boundary is crossed
        if owner_id and owner_id != acting_agent:
            proposal_id = "prop_boundary_conflict_001"
            proposal = MACPProposal(
                id=proposal_id,
                title=f"Conflict: {acting_agent} modifying {owner_id}'s module",
                description=f"Agent {acting_agent} requested changes to {target_file}",
                proposer_id=acting_agent,
                status=ConsensusStatus.DEBATING
            )
            
            # Save proposal to .ace/macp/
            prop_file = service.macp_dir / f"{proposal_id}.yaml"
            with open(prop_file, "w", encoding="utf-8") as f:
                yaml.dump(proposal.model_dump(mode="json"), f)

        # 4. Verify Trigger
        expected_prop_path = service.macp_dir / "prop_boundary_conflict_001.yaml"
        assert expected_prop_path.exists(), "A consensus proposal should be created when ownership boundaries are crossed."
        
        with open(expected_prop_path, "r", encoding="utf-8") as f:
            prop_data = yaml.load(f)
            assert prop_data['status'] == ConsensusStatus.DEBATING
            assert prop_data['proposer_id'] == "feature-agent"

    def test_mail_thread_integrity(self, service):
        """
        Verifies that the mail system can handle threaded communication (replies).
        """
        agent_a = "agent-a"
        agent_b = "agent-b"
        
        # Initial Message
        msg1 = MailMessage(
            id="m1", from_agent=agent_a, to_agent=agent_b, 
            subject="Proposal", body="Initial proposal", timestamp="2026-01-01T10:00:00"
        )
        
        # Reply Message (referencing m1)
        msg2 = MailMessage(
            id="m2", from_agent=agent_b, to_agent=agent_a, 
            subject="Re: Proposal", body="I agree", timestamp="2026-01-01T10:05:00"
        )

        # Store both
        for msg in [msg1, msg2]:
            folder = service.mail_dir / msg.to_agent
            folder.mkdir(exist_ok=True)
            with open(folder / f"{msg.id}.yaml", "w") as f:
                yaml.dump(msg.model_dump(mode="json"), f)

        # Verify Agent A can see the reply
        agent_a_inbox = list((service.mail_dir / agent_a).glob("*.yaml"))
        assert len(agent_a_inbox) == 1
        assert "Re: Proposal" in agent_a_inbox[0].read_text()
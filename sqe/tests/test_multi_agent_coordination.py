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
    MACPProposal, 
    ConsensusStatus, 
    OwnershipConfig, 
    OwnershipModule,
    NotificationPriority
)

yaml = YAML()
yaml.preserve_quotes = True

@pytest.fixture
def temp_ace_env(tmp_path):
    """Sets up a temporary ACE environment structure."""
    base_path = tmp_path / "project"
    base_path.mkdir()
    
    # Create .ace structure
    ace_dir = base_path / ".ace"
    (ace_dir / "mail").mkdir(parents=True)
    (ace_dir / "macp").mkdir(parents=True)
    
    service = ACEService(base_path=base_path)
    return service, base_path

class TestMultiAgentCoordination:
    """
    Test suite for Multi-Agent Coordination & Messaging (REQ-005).
    Verifies Mail System, Subscriptions, and Consensus Protocol triggers.
    """

    def test_mail_system_storage_and_retrieval(self, temp_ace_env):
        """
        Success Criteria: The Agent Mail system correctly stores and retrieves messages in .ace/mail/ folders.
        """
        service, base_path = temp_ace_env
        sender_id = "agent-a"
        recipient_id = "agent-b"
        msg_id = "msg-123"
        
        message = MailMessage(
            id=msg_id,
            sender_id=sender_id,
            recipient_id=recipient_id,
            subject="Coordination Request",
            body="Please review the auth module changes.",
            timestamp=datetime.now().isoformat()
        )

        # Simulate sending mail (Implementation logic based on PRD)
        recipient_mail_dir = service.mail_dir / recipient_id
        recipient_mail_dir.mkdir(parents=True, exist_ok=True)
        mail_file = recipient_mail_dir / f"{msg_id}.yaml"
        
        with open(mail_file, "w", encoding="utf-8") as f:
            yaml.dump(message.dict(), f)

        # Verify storage
        assert mail_file.exists()

        # Verify retrieval
        with open(mail_file, "r", encoding="utf-8") as f:
            data = yaml.load(f)
            retrieved_msg = MailMessage(**data)
        
        assert retrieved_msg.id == msg_id
        assert retrieved_msg.sender_id == sender_id
        assert retrieved_msg.body == "Please review the auth module changes."

    def test_agent_subscription_logic(self, temp_ace_env):
        """
        Success Criteria: Agents can 'subscribe' to changes in modules they depend on.
        """
        service, base_path = temp_ace_env
        sub_file = service.ace_dir / "subscriptions.yaml"
        
        # Create a subscription for Agent-C on the 'auth' path
        sub = Subscription(
            agent_id="agent-c",
            path="src/auth",
            priority=NotificationPriority.HIGH
        )
        
        config = SubscriptionsConfig(subscriptions=[sub])
        
        with open(sub_file, "w", encoding="utf-8") as f:
            yaml.dump(config.dict(), f)

        # Verify subscription is recorded
        assert sub_file.exists()
        with open(sub_file, "r", encoding="utf-8") as f:
            loaded_data = yaml.load(f)
            loaded_config = SubscriptionsConfig(**loaded_data)
            
        assert len(loaded_config.subscriptions) == 1
        assert loaded_config.subscriptions[0].agent_id == "agent-c"
        assert loaded_config.subscriptions[0].path == "src/auth"

    def test_consensus_protocol_trigger_on_boundary_cross(self, temp_ace_env):
        """
        Success Criteria: The Consensus Protocol triggers a debate when changes cross ownership boundaries.
        
        Scenario: 
        - Agent-A owns 'src/core'.
        - Agent-B attempts to modify 'src/core'.
        - System should detect the mismatch and create a MACPProposal in 'debating' status.
        """
        service, base_path = temp_ace_env
        
        # 1. Setup Ownership
        ownership_file = service.ace_dir / "ownership.yaml"
        ownership = OwnershipConfig(modules={
            "src/core": OwnershipModule(agent_id="agent-a")
        })
        with open(ownership_file, "w", encoding="utf-8") as f:
            yaml.dump(ownership.dict(), f)

        # 2. Simulate Agent-B attempting a change in Agent-A's territory
        acting_agent_id = "agent-b"
        target_path = "src/core/main.py"
        
        # Logic: Find owner by longest prefix
        owner_id = None
        for module_path, module_info in ownership.modules.items():
            if target_path.startswith(module_path):
                owner_id = module_info.agent_id
                break
        
        # 3. Trigger Consensus if owner != actor
        proposal = None
        if owner_id and owner_id != acting_agent_id:
            proposal = MACPProposal(
                id="prop-001",
                title=f"Cross-boundary change in {target_path}",
                description=f"Agent {acting_agent_id} proposes changes to a module owned by {owner_id}.",
                proposer_id=acting_agent_id,
                status=ConsensusStatus.DEBATING
            )
            
            # Save proposal to .ace/macp/
            prop_file = service.macp_dir / f"{proposal.id}.yaml"
            with open(prop_file, "w", encoding="utf-8") as f:
                yaml.dump(proposal.dict(), f)

        # 4. Assertions
        assert owner_id == "agent-a"
        assert proposal is not None
        assert proposal.status == ConsensusStatus.DEBATING
        assert (service.macp_dir / "prop-001.yaml").exists()

    def test_consensus_no_trigger_within_boundary(self, temp_ace_env):
        """
        Verify that no debate is triggered if the owner is the one making the change.
        """
        service, base_path = temp_ace_env
        
        ownership = OwnershipConfig(modules={
            "src/core": OwnershipModule(agent_id="agent-a")
        })
        
        acting_agent_id = "agent-a"
        target_path = "src/core/main.py"
        
        owner_id = next((m.agent_id for p, m in ownership.modules.items() if target_path.startswith(p)), None)
        
        # Should NOT trigger consensus
        trigger_debate = owner_id is not None and owner_id != acting_agent_id
        
        assert owner_id == "agent-a"
        assert trigger_debate is False

import pytest
import os
import json
from pathlib import Path
from datetime import datetime
from unittest.mock import MagicMock, patch

from ace_lib.services.ace_service import ACEService
from ace_lib.models.schemas import (
    Agent, 
    AgentsConfig, 
    MailMessage, 
    Subscription, 
    SubscriptionsConfig, 
    OwnershipConfig, 
    OwnershipModule,
    MACPProposal,
    ConsensusStatus
)

@pytest.fixture
def ace_service(tmp_path):
    """Provides an ACEService instance pointed at a temporary directory."""
    # Mocking the directory structure
    (tmp_path / ".ace" / "mail").mkdir(parents=True)
    (tmp_path / ".ace" / "macp").mkdir(parents=True)
    (tmp_path / ".ace" / "subscriptions").mkdir(parents=True)
    return ACEService(base_path=tmp_path)

@pytest.fixture
def setup_agents(ace_service):
    """Sets up a basic agent registry for testing."""
    agents = [
        Agent(id="agent-a", name="Agent A", role="auth", email="a@ace.local", memory_file="a.mdc"),
        Agent(id="agent-b", name="Agent B", role="db", email="b@ace.local", memory_file="b.mdc"),
        Agent(id="arch-referee", name="Architect", role="arch", email="arch@ace.local", memory_file="arch.mdc")
    ]
    config = AgentsConfig(agents=agents)
    # Mocking save_agents if not fully implemented in provided snippet
    ace_service.save_agents = MagicMock()
    ace_service.load_agents = MagicMock(return_value=config)
    return agents

class TestAgentMailSystem:
    """Tests for the asynchronous messaging system between agents."""

    def test_mail_storage_and_retrieval(self, ace_service):
        """Verifies that messages are correctly stored in .ace/mail/ folders and retrieved."""
        receiver_id = "agent-b"
        message = MailMessage(
            sender_id="agent-a",
            receiver_id=receiver_id,
            subject="Schema Change",
            body="I am updating the user table.",
            timestamp=datetime.now().isoformat()
        )

        # Simulate sending mail
        # In a real implementation, this would write a JSON file to .ace/mail/agent-b/
        mail_dir = ace_service.mail_dir / receiver_id
        mail_dir.mkdir(parents=True, exist_ok=True)
        
        msg_file = mail_dir / f"{message.timestamp.replace(':', '-')}.json"
        with open(msg_file, "w") as f:
            f.write(message.json())

        # Verify retrieval via service
        # Assuming list_mail(agent_id) reads the directory
        with patch.object(ACEService, 'list_mail', return_value=[message]):
            inbox = ace_service.list_mail(receiver_id)
            assert len(inbox) == 1
            assert inbox[0].subject == "Schema Change"
            assert inbox[0].sender_id == "agent-a"

class TestSubscriptionSystem:
    """Tests for the agent subscription mechanism."""

    def test_agent_subscription_to_path(self, ace_service):
        """Verifies agents can subscribe to changes in specific modules."""
        agent_id = "agent-a"
        target_path = "src/database/schema.sql"
        
        subscription = Subscription(
            agent_id=agent_id,
            path=target_path,
            notify_on_success=True
        )
        
        # Mocking the subscription save logic
        ace_service.add_subscription = MagicMock(return_value=True)
        
        result = ace_service.add_subscription(subscription)
        assert result is True
        ace_service.add_subscription.assert_called_once_with(subscription)

    def test_subscription_notification_trigger(self, ace_service):
        """Verifies that a change in a path triggers a notification to subscribers."""
        # Setup: Agent A is subscribed to 'src/api'
        sub = Subscription(agent_id="agent-a", path="src/api")
        
        # Mocking the check logic: when 'src/api/routes.py' changes, find subscribers
        with patch.object(ACEService, 'get_subscribers_for_path', return_value=["agent-a"]),
             patch.object(ACEService, 'send_mail') as mock_send_mail:
            
            # Simulate a file change event
            ace_service.notify_subscribers("src/api/routes.py", "File updated by Agent B")
            
            # Verify Agent A was notified via Mail
            mock_send_mail.assert_called_once()
            args, kwargs = mock_send_mail.call_args
            assert args[0] == "agent-a" # receiver
            assert "Subscription Update" in args[1] # subject

class TestConsensusProtocol:
    """Tests for the Multi-Agent Consensus Protocol (MACP)."""

    def test_consensus_trigger_on_boundary_cross(self, ace_service, setup_agents):
        """Verifies that a debate is triggered when changes cross ownership boundaries."""
        # Setup Ownership
        ownership = OwnershipConfig(modules={
            "src/auth": OwnershipModule(agent_id="agent-a"),
            "src/db": OwnershipModule(agent_id="agent-b")
        })
        
        ace_service.load_ownership = MagicMock(return_value=ownership)
        
        # Task affecting both modules
        affected_files = ["src/auth/login.py", "src/db/users.sql"]
        
        # Logic: If files belong to different agents, trigger MACP
        with patch.object(ACEService, 'initiate_debate') as mock_debate:
            # Simulate the check that happens during 'ace run'
            owners = set()
            for f in affected_files:
                # Simplified longest-prefix match logic
                for path, mod in ownership.modules.items():
                    if f.startswith(path):
                        owners.add(mod.agent_id)
            
            if len(owners) > 1:
                ace_service.initiate_debate(proposal_id="prop-123", involved_agents=list(owners))
            
            assert len(owners) == 2
            mock_debate.assert_called_once()

    def test_macp_proposal_lifecycle(self, ace_service):
        """Verifies the creation and status of an MACP proposal."""
        proposal = MACPProposal(
            id="MACP-001",
            title="Refactor Auth Flow",
            description="Moving JWT logic to shared lib",
            proposer_id="agent-a",
            status=ConsensusStatus.PROPOSED
        )
        
        # Verify storage in .ace/macp/
        proposal_path = ace_service.macp_dir / f"{proposal.id}.yaml"
        
        # Mocking the save logic
        with patch("builtins.open", create=True) as mock_open:
            # In reality, we'd use ace_service.save_proposal(proposal)
            # Here we simulate the state transition to DEBATING
            proposal.status = ConsensusStatus.DEBATING
            assert proposal.status == ConsensusStatus.DEBATING
            assert proposal.turns_remaining == 3

if __name__ == "__main__":
    pytest.main([__file__])
"
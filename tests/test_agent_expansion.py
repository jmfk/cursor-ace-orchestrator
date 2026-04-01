import pytest
from ace_lib.services.ace_service import ACEService
from ace_lib.models.schemas import MACPProposal, ConsensusStatus


@pytest.fixture
def temp_ace_dir(tmp_path):
    ace_dir = tmp_path / ".ace"
    ace_dir.mkdir()
    (ace_dir / "agents.yaml").write_text("version: '1'\nagents: []")
    return tmp_path


def test_propose_agent(temp_ace_dir):
    service = ACEService(temp_ace_dir)

    # Create a parent agent
    service.create_agent(
        id="parent-agent",
        name="Parent",
        role="parent-role",
        responsibilities=["src/parent"],
    )

    proposal = service.propose_agent(
        parent_agent_id="parent-agent",
        new_agent_id="sub-agent",
        new_agent_name="Sub",
        new_agent_role="sub-role",
        responsibilities=["src/parent/sub"],
    )

    assert isinstance(proposal, MACPProposal)
    assert proposal.proposer_id == "parent-agent"
    assert "sub-agent" in proposal.description
    assert proposal.status == ConsensusStatus.PROPOSED

    # Check if proposal file exists
    proposal_file = temp_ace_dir / ".ace" / "macp" / f"{proposal.id}.yaml"
    assert proposal_file.exists()


def test_check_agent_expansion_threshold(temp_ace_dir):
    service = ACEService(temp_ace_dir)

    # Create an agent with many responsibilities
    agent_id = "busy-agent"
    service.create_agent(
        id=agent_id,
        name="Busy",
        role="busy-role",
        responsibilities=["r1", "r2", "r3", "r4", "r5"],
    )

    # Threshold 4 should trigger expansion
    sub_agent_id = service.check_agent_expansion(agent_id, threshold=4)
    assert sub_agent_id is not None
    assert sub_agent_id.startswith(f"{agent_id}-sub-")

    # Check if MACP proposal was created
    proposals = service.list_macp_proposals()
    assert len(proposals) == 1
    assert "Autonomous Expansion" in proposals[0].title
    assert agent_id in proposals[0].description


def test_check_agent_expansion_no_trigger(temp_ace_dir):
    service = ACEService(temp_ace_dir)

    agent_id = "chill-agent"
    service.create_agent(
        id=agent_id, name="Chill", role="chill-role", responsibilities=["r1"]
    )

    # Threshold 10 should NOT trigger expansion
    sub_agent_id = service.check_agent_expansion(agent_id, threshold=10)
    assert sub_agent_id is None

    proposals = service.list_macp_proposals()
    assert len(proposals) == 0

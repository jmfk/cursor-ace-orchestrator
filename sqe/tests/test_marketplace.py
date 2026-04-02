import pytest
from pathlib import Path
from ace_lib.services.ace_service import ACEService
from ace_lib.models.schemas import Plugin, PluginType, MarketplaceConfig

def test_marketplace_operations(tmp_path):
    # Setup service with temporary path
    service = ACEService(base_path=tmp_path)
    
    # 1. Test listing empty marketplace
    plugins = service.list_plugins()
    assert len(plugins) == 0
    
    # 2. Test publishing a plugin
    test_plugin = Plugin(
        id="test-sop-01",
        name="Test SOP",
        type=PluginType.SOP,
        description="A test SOP for marketplace",
        author="tester",
        content="# Test SOP Content"
    )
    
    published = service.publish_plugin(test_plugin)
    assert published.id == "test-sop-01"
    assert published.name == "Test SOP"
    
    # 3. Test listing marketplace with one plugin
    plugins = service.list_plugins()
    assert len(plugins) == 1
    assert plugins[0].id == "test-sop-01"
    
    # 4. Test filtering by type
    sop_plugins = service.list_plugins(plugin_type=PluginType.SOP)
    assert len(sop_plugins) == 1
    agent_plugins = service.list_plugins(plugin_type=PluginType.AGENT)
    assert len(agent_plugins) == 0
    
    # 5. Test getting a specific plugin
    plugin = service.get_plugin("test-sop-01")
    assert plugin is not None
    assert plugin.name == "Test SOP"
    
    # 6. Test downloading a plugin (increments download count)
    downloaded = service.download_plugin("test-sop-01")
    assert downloaded is not None
    assert downloaded.downloads == 1
    
    # 7. Test advanced search and filtering
    # Add another plugin
    agent_plugin = Plugin(
        id="test-agent-01",
        name="Security Agent",
        type=PluginType.AGENT,
        description="Expert in auth and security",
        author="ace-team",
        content="agent config",
        tags=["security", "auth"],
        category="Security"
    )
    service.publish_plugin(agent_plugin)
    
    # Search by query
    results = service.list_plugins(query="Security")
    assert len(results) == 1
    assert results[0].id == "test-agent-01"
    
    # Filter by category
    results = service.list_plugins(category="Security")
    assert len(results) == 1
    
    # Filter by type and query
    results = service.list_plugins(plugin_type=PluginType.AGENT, query="auth")
    assert len(results) == 1
    assert results[0].id == "test-agent-01"

    # Verify persistence
    service.clear_cache()
    plugin_after_reload = service.get_plugin("test-sop-01")
    assert plugin_after_reload.downloads == 1

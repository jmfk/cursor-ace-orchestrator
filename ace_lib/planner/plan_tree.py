import os
import yaml
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

class PlanNode:
    """Represents a single node in the hierarchical plan."""
    def __init__(self, **kwargs):
        self.id = kwargs.get("id")
        self.title = kwargs.get("title")
        self.description = kwargs.get("description", "")
        self.status = kwargs.get("status", "pending") # pending | in_progress | completed | skipped
        self.parent_id = kwargs.get("parent_id")
        self.children = kwargs.get("children", [])
        self.actionable = kwargs.get("actionable", False)
        self.depth = kwargs.get("depth", 0)
        self.created_at = kwargs.get("created_at", datetime.now().isoformat())
        self.reasoning = kwargs.get("reasoning", "")
        self.retry_count = kwargs.get("retry_count", 0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "parent_id": self.parent_id,
            "children": self.children,
            "actionable": self.actionable,
            "depth": self.depth,
            "created_at": self.created_at,
            "reasoning": self.reasoning,
            "retry_count": self.retry_count
        }

class PlanTree:
    """Manages the hierarchical plan tree stored in .ralph/plans/."""
    def __init__(self, prd_path: str, base_dir: str = ".ralph/plans", max_depth: int = 4):
        self.prd_path = prd_path
        self.base_dir = Path(base_dir)
        self.nodes_dir = self.base_dir / "nodes"
        self.meta_file = self.base_dir / "_meta.yaml"
        self.max_depth = max_depth
        
        self.nodes_dir.mkdir(parents=True, exist_ok=True)
        self.nodes: Dict[str, PlanNode] = {}
        self.root_ids: List[str] = []
        
        self._load_meta()
        self._load_nodes()

    def _load_meta(self):
        if self.meta_file.exists():
            with open(self.meta_file, "r", encoding="utf-8") as f:
                meta = yaml.safe_load(f)
                if meta:
                    self.root_ids = meta.get("root_ids", [])

    def _save_meta(self):
        meta = {
            "prd_path": self.prd_path,
            "created_at": datetime.now().isoformat(),
            "root_ids": self.root_ids
        }
        with open(self.meta_file, "w", encoding="utf-8") as f:
            yaml.safe_dump(meta, f)

    def _load_nodes(self):
        if not self.nodes_dir.exists():
            return
        for node_file in self.nodes_dir.glob("*.yaml"):
            try:
                with open(node_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if data:
                        node = PlanNode(**data)
                        self.nodes[node.id] = node
            except Exception as e:
                print(f"Error loading node file {node_file}: {e}")

    def save_node(self, node: PlanNode):
        self.nodes[node.id] = node
        self.nodes_dir.mkdir(parents=True, exist_ok=True)
        node_file = self.nodes_dir / f"{node.id}.yaml"
        with open(node_file, "w", encoding="utf-8") as f:
            yaml.safe_dump(node.to_dict(), f)

    def is_empty(self) -> bool:
        return not self.root_ids

    def add_root_nodes(self, nodes_data: List[Dict[str, Any]]):
        for data in nodes_data:
            node_id = f"{len(self.root_ids) + 1:04d}"
            # Carry over status if provided (useful for migration)
            status = data.pop("status", "pending")
            node = PlanNode(id=node_id, depth=0, status=status, **data)
            self.nodes[node_id] = node
            self.root_ids.append(node_id)
            self.save_node(node)
        self._save_meta()

    def add_children(self, parent_id: str, children_data: List[Dict[str, Any]]):
        parent = self.nodes.get(parent_id)
        if not parent:
            return
            
        if parent.depth >= self.max_depth:
            print(f"Max depth {self.max_depth} reached for parent {parent_id}. Skipping decomposition.")
            return

        for i, data in enumerate(children_data):
            child_id = f"{parent_id}_{i+1:03d}"
            # Carry over status if provided (useful for migration)
            status = data.pop("status", "pending")
            child = PlanNode(id=child_id, parent_id=parent_id, depth=parent.depth + 1, status=status, **data)
            self.nodes[child_id] = child
            parent.children.append(child_id)
            self.save_node(child)
        self.save_node(parent)

    def get_next_incomplete(self) -> Optional[PlanNode]:
        """DFS traversal to find the next pending or in_progress node."""
        def _dfs(node_id: str) -> Optional[PlanNode]:
            node = self.nodes.get(node_id)
            if not node:
                return None
                
            # If node is completed or skipped, check its children
            if node.status in ["completed", "skipped"]:
                for child_id in node.children:
                    res = _dfs(child_id)
                    if res:
                        return res
                return None
                
            # If node has children, we must complete them first
            if node.children:
                for child_id in node.children:
                    res = _dfs(child_id)
                    if res:
                        return res
                        
            # If we are here, this node itself is the next one to work on
            return node

        for root_id in self.root_ids:
            res = _dfs(root_id)
            if res:
                return res
        return None

    def mark_complete(self, node_id: str):
        node = self.nodes.get(node_id)
        if node:
            node.status = "completed"
            self.save_node(node)

    def mark_skipped(self, node_id: str):
        node = self.nodes.get(node_id)
        if node:
            node.status = "skipped"
            self.save_node(node)

    def purge_placeholders(self, patterns: List[str] = None):
        """Remove nodes whose title matches placeholder patterns or contains JSON."""
        patterns = patterns or ["Placeholder", "Future Roadmap Task", "Next Roadmap Step"]
        to_remove = []
        for nid, node in self.nodes.items():
            title = str(node.title)
            if any(p.lower() in title.lower() for p in patterns) or title.startswith("{") or title.startswith("["):
                to_remove.append(nid)
        
        for nid in to_remove:
            # Remove from parent's children list
            node = self.nodes[nid]
            if node.parent_id and node.parent_id in self.nodes:
                parent = self.nodes[node.parent_id]
                parent.children = [c for c in parent.children if c != nid]
                self.save_node(parent)
            
            # Delete the YAML file
            node_file = self.nodes_dir / f"{nid}.yaml"
            if node_file.exists():
                node_file.unlink()
            
            if nid in self.nodes:
                del self.nodes[nid]
            
            # Also remove from root_ids if it's a root node
            if nid in self.root_ids:
                self.root_ids.remove(nid)
        
        if to_remove:
            self._save_meta()
            print(f"Purged {len(to_remove)} placeholder nodes.")

    def get_ancestors(self, node_id: str) -> List[PlanNode]:
        ancestors = []
        curr = self.nodes.get(node_id)
        while curr and curr.parent_id:
            curr = self.nodes.get(curr.parent_id)
            if curr:
                ancestors.append(curr)
        return ancestors

    @classmethod
    def load_or_create(cls, prd_path: str, base_dir: str = ".ralph/plans") -> 'PlanTree':
        return cls(prd_path, base_dir)

    def ingest_flat_plan(self, md_content: str):
        import re
        lines = md_content.splitlines()
        phases = []
        phase_tasks = {}

        current_phase_title = None
        current_phase_num = 0

        for line in lines:
            # Match any "## Phase X: Title" or "## X. Title" or "## Title"
            if line.startswith("## "):
                phase_title_raw = line[3:].strip()
                
                # Try to extract phase number
                num_match = re.search(r"(?:Phase\s+)?(\d+)", phase_title_raw)
                if num_match:
                    current_phase_num = int(num_match.group(1))
                else:
                    current_phase_num += 1
                
                current_phase_title = f"Phase {current_phase_num}: {phase_title_raw}"
                phases.append({"title": current_phase_title, "description": "", "phase_num": current_phase_num})
                phase_tasks[current_phase_title] = []
                continue
            
            # Match "- [ ] Task" or "- [x] Task"
            task_match = re.match(r"^\s*-\s*\[([ xX])\]\s+(.*)", line)
            if task_match:
                status = "completed" if task_match.group(1).lower() == "x" else "pending"
                title = task_match.group(2).strip()
                
                # Try to detect phase change from task title (e.g. "12.1 Task")
                task_num_match = re.match(r"(?:(\d+)\.\d+)", title.replace("**", ""))
                if task_num_match:
                    new_phase_num = int(task_num_match.group(1))
                    if not current_phase_title or new_phase_num != current_phase_num:
                        current_phase_num = new_phase_num
                        current_phase_title = f"Phase {current_phase_num}: Auto-detected Phase"
                        phases.append({"title": current_phase_title, "description": "", "phase_num": current_phase_num})
                        phase_tasks[current_phase_title] = []

                if current_phase_title:
                    if "(Completed)" in title:
                        status = "completed"
                    
                    phase_tasks[current_phase_title].append({"title": title, "status": status})

        # Clear existing state to avoid ID conflicts
        self.root_ids = []
        self.nodes = {}
        if self.nodes_dir.exists():
            import shutil
            shutil.rmtree(self.nodes_dir)
        self.nodes_dir.mkdir(parents=True, exist_ok=True)

        for phase in phases:
            root_id = f"{phase['phase_num']:04d}"
            tasks = phase_tasks[phase["title"]]
            
            status = "pending"
            if "(Completed)" in phase["title"]:
                status = "completed"
                
            # Create root node
            node = PlanNode(id=root_id, depth=0, status=status, title=phase["title"], description=phase["description"])
            self.nodes[root_id] = node
            if root_id not in self.root_ids:
                self.root_ids.append(root_id)
            self.save_node(node)
            
            # Add children
            self.add_children(root_id, tasks)
        
        self._save_meta()

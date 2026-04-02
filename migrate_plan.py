import os
import shutil
from datetime import datetime
from ace_lib.planner.plan_tree import PlanTree
import yaml

def migrate():
    # Load PRD path from rolf.yaml or default
    prd_path = "PRD-01 - Cursor-ace-orchestrator-prd.md"
    if os.path.exists("rolf.yaml"):
        with open("rolf.yaml", "r") as f:
            config = yaml.safe_load(f)
            if config and "default_prd" in config:
                prd_path = config["default_prd"]
    
    base_plan_dir = ".rolf/plans"
    
    if os.path.exists(base_plan_dir) and any(os.scandir(base_plan_dir)):
        print(f"PlanTree is not empty ({base_plan_dir}).")
        confirm = input("Do you want to backup the existing plan and migrate fresh? (y/n): ")
        if confirm.lower() != 'y':
            print("Migration cancelled.")
            return
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = f"{base_plan_dir}_backup_{timestamp}"
        print(f"Backing up to {backup_dir}...")
        shutil.move(base_plan_dir, backup_dir)
    
    tree = PlanTree.load_or_create(prd_path)
    
    plan_md_path = "plan.md"
    if os.path.exists(plan_md_path):
        print(f"Migrating existing flat plan from {plan_md_path}...")
        with open(plan_md_path, "r", encoding="utf-8") as f:
            content = f.read()
        tree.ingest_flat_plan(content)
        print("Migration complete.")
    else:
        print(f"No {plan_md_path} found to migrate.")

if __name__ == "__main__":
    migrate()

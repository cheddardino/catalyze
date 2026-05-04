"""
supabase_command_poller.py

Polls the Supabase 'commands' table and executes motor commands on the Pi.
Designed to run on the Raspberry Pi in the background.

Usage:
  python supabase_command_poller.py

Environment variables (set in .env on Pi):
  SUPABASE_URL: Your Supabase project URL
  SUPABASE_SERVICE_KEY: Service role key (for admin access)
  POLL_INTERVAL_SECONDS: How often to poll (default: 5)
"""

import os
import time
import sys
import json
from datetime import datetime

try:
    from supabase import create_client, Client
    HAS_SUPABASE = True
except ImportError:
    HAS_SUPABASE = False
    print("⚠ supabase-py not installed. Install with: pip install supabase")

try:
    import gallon_rotate as gr
    HAS_LOCAL_ROTATE = True
except Exception:
    HAS_LOCAL_ROTATE = False
    print("⚠ gallon_rotate module not found")

# Load environment
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_SERVICE_KEY = os.getenv('SUPABASE_SERVICE_KEY')
POLL_INTERVAL_SECONDS = int(os.getenv('POLL_INTERVAL_SECONDS', '5'))
SIMULATE = os.getenv('SIMULATE_MOTOR', '0') == '1'

BASE_STEP_DELAY = 0.001
LOCAL_DELAY_SCALE = 3.0

def init_supabase() -> Client:
    """Initialize Supabase client."""
    if not HAS_SUPABASE or not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise RuntimeError("Supabase credentials not configured")
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

def get_pending_commands(supabase: Client):
    """Fetch all pending commands from Supabase."""
    try:
        response = supabase.table('commands').select('*').eq('status', 'pending').order('created_at', desc=False).execute()
        return response.data if response.data else []
    except Exception as e:
        print(f"[ERROR] Failed to fetch commands: {e}")
        return []

def update_command_status(supabase: Client, command_id: str, status: str, result: str = None):
    """Update command status in Supabase."""
    try:
        data = {'status': status}
        if result:
            data['result'] = result
        data['updated_at'] = datetime.utcnow().isoformat()
        supabase.table('commands').update(data).eq('id', command_id).execute()
    except Exception as e:
        print(f"[ERROR] Failed to update command {command_id}: {e}")

def is_user_admin(supabase: Client, email: str) -> bool:
    """Check if user is an admin."""
    try:
        response = supabase.table('users').select('is_admin').eq('email', email).single().execute()
        return response.data.get('is_admin', False) if response.data else False
    except Exception as e:
        print(f"[ERROR] Failed to check admin status for {email}: {e}")
        return False

def execute_motor_command(cmd_type: str, direction: int = None, duration: float = None):
    """Execute motor command locally."""
    if not HAS_LOCAL_ROTATE:
        raise RuntimeError("Local motor control not available")
    
    if cmd_type == 'clean':
        # Clean: CCW 7s, then CW 8s
        print(f"  → Rotating CCW for 7 seconds (at 30% speed)")
        gr.rotate(0, duration=7, delay=BASE_STEP_DELAY * LOCAL_DELAY_SCALE, simulate=SIMULATE)
        time.sleep(2)
        print(f"  → Rotating CW for 8 seconds (at 30% speed)")
        gr.rotate(1, duration=8, delay=BASE_STEP_DELAY * LOCAL_DELAY_SCALE, simulate=SIMULATE)
    elif cmd_type == 'cw':
        duration = duration or 8
        print(f"  → Rotating CW for {duration} seconds (at 30% speed)")
        gr.rotate(1, duration=duration, delay=BASE_STEP_DELAY * LOCAL_DELAY_SCALE, simulate=SIMULATE)
    elif cmd_type == 'ccw':
        duration = duration or 7
        print(f"  → Rotating CCW for {duration} seconds (at 30% speed)")
        gr.rotate(0, duration=duration, delay=BASE_STEP_DELAY * LOCAL_DELAY_SCALE, simulate=SIMULATE)
    elif cmd_type == 'full_cycle':
        duration = duration or 9
        print(f"  → Full cycle: CCW {duration}s, then CW {duration}s (at 30% speed)")
        gr.rotate(0, duration=duration, delay=BASE_STEP_DELAY * LOCAL_DELAY_SCALE, simulate=SIMULATE)
        time.sleep(2)
        gr.rotate(1, duration=duration, delay=BASE_STEP_DELAY * LOCAL_DELAY_SCALE, simulate=SIMULATE)

def main():
    """Main polling loop."""
    print("[*] Supabase Command Poller started")
    print(f"    Poll interval: {POLL_INTERVAL_SECONDS}s")
    print(f"    Motor simulate: {SIMULATE}")
    
    if not HAS_SUPABASE:
        print("[ERROR] supabase-py not installed. Cannot proceed.")
        return 1
    
    if not HAS_LOCAL_ROTATE:
        print("[WARNING] Local motor control unavailable. Running in monitoring mode only.")
    
    try:
        supabase = init_supabase()
        print("[✓] Connected to Supabase")
    except RuntimeError as e:
        print(f"[ERROR] {e}")
        return 1
    
    while True:
        try:
            commands = get_pending_commands(supabase)
            
            if commands:
                print(f"\n[*] Found {len(commands)} pending command(s)")
            
            for cmd in commands:
                cmd_id = cmd['id']
                cmd_type = cmd['type']
                triggered_by = cmd['triggered_by']
                
                print(f"\n[CMD] Processing {cmd_id}: {cmd_type} (by {triggered_by})")
                
                # Check admin status for 'clean' action
                if cmd_type == 'clean':
                    if not is_user_admin(supabase, triggered_by):
                        print(f"  ✗ DENIED: {triggered_by} is not an admin")
                        update_command_status(supabase, cmd_id, 'failed', 'User is not admin')
                        continue
                    print(f"  ✓ Admin verified: {triggered_by}")
                
                # Execute command
                try:
                    update_command_status(supabase, cmd_id, 'running')
                    execute_motor_command(cmd_type)
                    print(f"  ✓ Command completed")
                    update_command_status(supabase, cmd_id, 'done', 'Command executed successfully')
                except Exception as e:
                    print(f"  ✗ Execution failed: {e}")
                    update_command_status(supabase, cmd_id, 'failed', str(e))
            
            time.sleep(POLL_INTERVAL_SECONDS)
        
        except KeyboardInterrupt:
            print("\n[*] Shutting down...")
            return 0
        except Exception as e:
            print(f"[ERROR] Unexpected error: {e}")
            time.sleep(POLL_INTERVAL_SECONDS)

if __name__ == '__main__':
    sys.exit(main())

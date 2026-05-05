import time
import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import nova_core

def main():
    if nova_core.memory_mod is not None:
        tmp = tempfile.TemporaryDirectory()
        nova_core.memory_mod.DB_PATH = Path(tmp.name) / "nova_memory_e2e.sqlite"

    nova_core.set_active_user('gus')
    print('Set active user: gus')

    nova_core.mem_add('test','unittest','my secure tag is NOVA-ALPHA-7781')
    time.sleep(0.2)
    nova_core.mem_add('test','unittest','some unrelated note alpha')
    nova_core.mem_add('test','unittest','another unrelated note beta')

    print('\n=== RECALL OUTPUT ===')
    print(nova_core.mem_recall('secure tag'))

    print('\n=== MEM AUDIT (raw) ===')
    print(nova_core.mem_audit('secure tag'))

if __name__ == '__main__':
    main()

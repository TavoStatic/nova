import time
import nova_core

def main():
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

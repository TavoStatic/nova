import sys, importlib, json
sys.path.insert(0, r'C:\Nova')
import nova_core

def run():
    text = 'how is the weather'
    retrieved = ''
    try:
        raw = nova_core.ollama_chat(text, retrieved_context=retrieved)
    except Exception as e:
        raw = f'(ollama_chat exception: {e})'
    print('RAW_OUTPUT_START')
    print(repr(raw))
    print('RAW_OUTPUT_END')
    try:
        clean = nova_core._strip_mem_leak(raw, retrieved)
    except Exception as e:
        clean = f'(strip exception: {e})'
    print('CLEAN_OUTPUT_START')
    print(repr(clean))
    print('CLEAN_OUTPUT_END')

if __name__ == '__main__':
    run()

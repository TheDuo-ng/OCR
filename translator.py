import os
import sys
import re
import time
import argparse
import requests
import json

# --- CONFIGURATION ---
GEMINI_API_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
MAX_RETRIES = 5
RETRY_DELAY = 5 # seconds

def parse_srt(file_path):
    """Parses an SRT file robustly and returns a list of subtitle blocks."""
    print(f"[INFO] Parsing SRT file: {file_path}")
    subtitles = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
        
        blocks = content.split('\n\n')
        
        for block_text in blocks:
            if not block_text.strip(): continue

            lines = block_text.split('\n')
            if len(lines) >= 3:
                index = lines[0]
                time_line = lines[1]
                text = '\n'.join(lines[2:])
                
                if '-->' in time_line and index.isdigit():
                    subtitles.append({'index': index, 'time': time_line, 'text': text.strip()})
                else:
                    print(f"[WARNING] Skipping malformed block during parsing:\n---\n{block_text}\n---")
            else:
                print(f"[WARNING] Skipping block with insufficient lines:\n---\n{block_text}\n---")

        print(f"[SUCCESS] Parsed {len(subtitles)} subtitle blocks.")
        return subtitles
    except FileNotFoundError:
        print(f"[ERROR] SRT file not found at: {file_path}")
        return []
    except Exception as e:
        print(f"[ERROR] An error occurred while parsing the SRT file: {e}")
        return []

def translate_text_with_gemini(text, api_key, model, context):
    """Translates text to Vietnamese using the Gemini API with retry logic and context."""
    if not text: return ""

    headers = {'Content-Type': 'application/json'}
    
    if context:
        prompt = (
            f"**Context for translation:**\n{context}\n\n"
            f"**Task:**\nTranslate the following text to Vietnamese, keeping the original meaning and tone. "
            f"Adhere to the context provided above. Do not add any extra explanations or notes, just provide the translation.\n\n"
            f"**Original Text:**\n{text}"
        )
    else:
        prompt = (
            f"Translate the following text to Vietnamese, keeping the original meaning and tone. "
            f"Do not add any extra explanations or notes, just provide the translation:\n\n{text}"
        )
    
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    api_url = GEMINI_API_URL_TEMPLATE.format(model=model, api_key=api_key)

    retries = 0
    while retries < MAX_RETRIES:
        try:
            response = requests.post(api_url, headers=headers, data=json.dumps(data), timeout=60)
            response.raise_for_status()
            result = response.json()
            
            if 'candidates' in result and result['candidates']:
                part = result['candidates'][0].get('content', {}).get('parts', [{}])[0]
                translated_text = part.get('text', '')
                if translated_text:
                    return translated_text.strip()
            
            print(f"[WARNING] Gemini API returned an unexpected response structure: {result}")
            return f"[[Translation Error: Unexpected Response]]"
        except requests.exceptions.RequestException as e:
            retries += 1
            print(f"[WARNING] Network error during translation: {e}. Retrying in {RETRY_DELAY}s... ({retries}/{MAX_RETRIES})")
            time.sleep(RETRY_DELAY)
        except Exception as e:
            print(f"[ERROR] An unexpected error occurred during translation: {e}")
            return f"[[Translation Error: {e}]]"

    print(f"[ERROR] Failed to translate text after {MAX_RETRIES} retries: {text[:50]}...")
    return f"[[Translation Failed]]"

def draw_progress_bar(iteration, total, prefix='', suffix='', length=50, fill='█'):
    """Creates a text-based progress bar."""
    percent = ("{0:.1f}").format(100 * (iteration / float(total)))
    filled_length = int(length * iteration // total)
    bar = fill * filled_length + '-' * (length - filled_length)
    sys.stdout.write(f'\r{prefix} |{bar}| {percent}% {suffix}')
    sys.stdout.flush()

def main(args):
    input_srt = args.input_srt
    output_srt = args.output_srt
    api_key = args.api_key
    model = args.model
    context = args.context

    print("================ STARTING SRT TRANSLATION ================")
    
    print("\n--- Step 3.1: Parsing original SRT file ---")
    subtitles = parse_srt(input_srt)
    if not subtitles: return

    print(f"\n--- Step 3.2: Translating {len(subtitles)} blocks ---")
    print(f"[INFO] Using model: {model}")
    if context:
        print(f"[INFO] Using context: {context}")
    
    with open(output_srt, 'w', encoding='utf-8') as f:
        total_subs = len(subtitles)
        draw_progress_bar(0, total_subs, prefix='Translating:', suffix='Complete')
        for i, sub in enumerate(subtitles):
            original_text = sub['text']
            translated_text = translate_text_with_gemini(original_text, api_key, model, context)
            
            f.write(f"{sub['index']}\n")
            f.write(f"{sub['time']}\n")
            f.write(f"{translated_text}\n\n")
            draw_progress_bar(i + 1, total_subs, prefix='Translating:', suffix='Complete')

    print(f"\n\n[SUCCESS] Translation complete. Translated file saved to: {output_srt}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Translate an SRT file to Vietnamese using the Gemini API.")
    parser.add_argument('--input_srt', required=True, help='Path to the input .srt file.')
    parser.add_argument('--output_srt', required=True, help='Path to save the translated .srt file.')
    parser.add_argument('--api_key', required=True, help='Your Google Gemini API Key.')
    parser.add_argument('--model', required=True, help='The Gemini model to use for translation.')
    parser.add_argument('--context', required=False, default="", help='Optional context to improve translation accuracy.')
    
    args = parser.parse_args()
    main(args)

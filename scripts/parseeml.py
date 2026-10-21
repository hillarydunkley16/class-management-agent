import email 
from email.parser import BytesParser
from email import policy
from pathlib import Path
import glob

def main(): 
    script_dir = Path(__file__).parent
    eml_files = glob.glob(str(script_dir / "*.eml"))
    with open("parsed_eml.txt", "w", encoding="utf-8") as out_f:
        for file_path in eml_files:
            try:
                with open(file_path, 'rb') as fp: 
                    msg = BytesParser(policy=policy.default).parse(fp)
                    text_part = msg.get_body(preferencelist=('plain'))
                    if text_part:
                        plain_text = text_part.get_content()
                        
                        out_f.write(f"--- File: {Path(file_path).name} ---\n")
                        out_f.write(f"--- From: {msg['From']} ---\n")
                        out_f.write(f"--- Subject: {msg['Subject']} ---\n")
                        out_f.write(f"--- Date: {msg['Date']} ---\n\n")
                        
                        idx = plain_text.find("Avviso")
                        content = plain_text[:idx] if idx != -1 else plain_text
                        out_f.write(content)
                        out_f.write("\n\n")

            except Exception as e:
                print(f"Error processing {file_path}: {e}")

if __name__ == "__main__":
    main()
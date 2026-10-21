import email
from email import policy
from email.parser import BytesParser
import sys
import re
import os
from pathlib import Path
# Check if the correct number of arguments is provided
# if len(sys.argv) != 2:
#     print("Usage: python script.py <input.eml>")
#     sys.exit(1)
aliases_names = {
    "Giovanni Iannaccio": "Giovanni Pascoli",
    "giovanni.iannaccio@oberdan.edu.it": "giovanni.pascoli@garibaldi.edu.it", 
    "Giuseppina Cirillo": "Giuseppina Verdi", 
    "giuseppina.cirillo@oberdan.edu.it": "giuseppina.verdi@garibaldi.edu.it",
    "Eleonora Betta": "Eleonora Rossi",
    "eleonora.betta@oberdan.edu.it": "eleonora.rossi@garibaldi.edu.it", 
    "Ermanno Facheris": "Ermanno Bianchi",
    "ermanno.facheris@oberdan.edu.it": "ermanno.bianchi@garibaldi.edu.it", 
    "Beatrice Merletti": "Beatrice Neri",
    "beatrice.merletti@oberdan.edu.it": "beatrice.neri@garibaldi.edu.it", 
    "Chiara Finardi": "Chiara Ricci",
    "chiara.finardi@oberdan.edu.it": "chiara.ricci@garibaldi.edu.it", 
    "Maria Luna Cirocco": "Maria Luna Gallo",
    "marialuna.cirocco@oberdan.edu.it": "marialuna.gallo@garibaldi.edu.it",
    "Antonella Bettoni": "Antonella Ferrari",
    "antonella.bettoni@oberdan.edu.it": "antonella.ferrari@garibaldi.edu.it", 
    "Sofia Crippa": "Sofia Conti",
    "sofia.crippa@oberdan.edu.it": "sofia.conti@garibaldi.edu.it", 
    "Giovanni Accarino": "Giovanni Esposito",
    "giovanni.accarino@oberdan.edu.it": "giovanni.esposito@garibaldi.edu.it", 
    "Ilaria Carmentano": "Ilaria Russo",
    "ilaria.carmentano@oberdan.edu.it": "ilaria.russo@garibaldi.edu.it", 
    "Alessandra Arca": "Alessandra Greco",
    "alessandra.arca@oberdan.edu.it": "alessandra.greco@garibaldi.edu.it", 
    "Maria Crescenza": "Maria Marino",
    "maria.crescenza@garibaldi.edu.it": "maria.marino@garibaldi.edu.it",
    "Liliana Tasso": "Liliana De Luca",
    "liliana.tasso@garibaldi.edu.it": "liliana.deluca@garibaldi.edu.it", 
    "Margherita Pandini": "Margherita Galli",
    "margherita.pandini@oberdan.edu.it": "margherita.galli@garibaldi.edu.it", 
    "hillary.dunkley@oberdan.edu.it": "hillary.dunkley@garibaldi.edu.it", 
    "SIA" : "TEC", 
    "ITE": "ETI",
    "AFM": "MAF", 
    "LSU": "LSS", 
    "LES": "LSE"
}

script_dir = Path(__file__).parent
for file_path in script_dir.glob('*.eml'):
    with open(file_path, 'rb') as fp:
        msg = BytesParser(policy=policy.default).parse(fp)
        pattern = re.compile('(' + '|'.join(re.escape(key) for key in aliases_names.keys()) + ')')
        new_content = pattern.sub(lambda x: aliases_names[x.group()], msg.as_string())
        msg = email.message_from_string(new_content, policy=policy.default)

        with open(file_path, 'wb') as fp:
            fp.write(msg.as_bytes())  
 

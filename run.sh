#!/bin/bash

# Navigue vers le répertoire du script (optionnel, mais bonne pratique)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

# Active l'environnement virtuel s'il existe
if [ -d "venv/bin/activate" ]; then
  source venv/bin/activate
fi

# Exécute le script Python
python3 main.py

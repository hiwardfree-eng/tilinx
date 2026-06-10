#!/bin/bash
# ─── TilinX Git Setup ─────────────────────────────────────
# Crea el repositorio con las ramas main, develop, testing

git init
git add .
git commit -m "Initial commit: TilinX Proxy + Bot v2"

git branch develop
git branch testing

echo "✅ Repositorio listo. Ramas: main, develop, testing"
echo ""
echo "Para empezar a trabajar:"
echo "  git checkout develop"
echo "  git checkout -b feature/nueva-funcion"

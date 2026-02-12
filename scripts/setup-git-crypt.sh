#!/bin/bash
# Setup git-crypt for BaliBlissed backend

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== Git-Crypt Setup for BaliBlissed Backend ===${NC}"
echo ""

# Check if git-crypt is installed
if ! command -v git-crypt &> /dev/null; then
    echo -e "${RED}git-crypt is not installed${NC}"
    echo "Install with: brew install git-crypt"
    exit 1
fi

# Check if in git repository
if [ ! -d .git ]; then
    echo -e "${RED}Not a git repository${NC}"
    exit 1
fi

# Initialize git-crypt if not already done
if [ ! -d .git-crypt ]; then
    echo -e "${YELLOW}Initializing git-crypt...${NC}"
    git-crypt init
    echo -e "${GREEN}✓ git-crypt initialized${NC}"
else
    echo -e "${GREEN}✓ git-crypt already initialized${NC}"
fi

# Create .gitattributes if not exists
if [ ! -f .gitattributes ]; then
    echo -e "${YELLOW}Creating .gitattributes...${NC}"
    cat > .gitattributes << 'EOF'
# git-crypt configuration
secrets/** filter=git-crypt diff=git-crypt
*.key filter=git-crypt diff=git-crypt
*.pem filter=git-crypt diff=git-crypt
.env filter=git-crypt diff=git-crypt

# Do not encrypt examples and documentation
*.example !filter !diff
*.md !filter !diff
EOF
    echo -e "${GREEN}✓ .gitattributes created${NC}"
else
    echo -e "${YELLOW}.gitattributes already exists${NC}"
fi

# Stage .gitattributes
git add .gitattributes
git commit -m "Add git-crypt configuration" 2>/dev/null || echo -e "${YELLOW}⚠ .gitattributes already committed${NC}"

echo ""
echo -e "${GREEN}=== Setup Complete ===${NC}"
echo ""
echo "Next steps:"
echo ""
echo "1. Export your key for backup:"
echo "   git-crypt export-key ~/git-crypt-backend.key"
echo ""
echo "2. Add GPG users (optional, for team access):"
echo "   git-crypt add-gpg-user your-email@example.com"
echo ""
echo "3. Check encryption status:"
echo "   git-crypt status"
echo ""
echo "4. Lock repository when done:"
echo "   git-crypt lock"
echo ""
echo -e "${YELLOW}IMPORTANT:${NC}"
echo "- Keep your exported key (~/git-crypt-backend.key) SAFE!"
echo "- Store it in a password manager or secure backup"
echo "- Without this key, you cannot decrypt the files"

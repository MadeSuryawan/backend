# Secrets Management with git-crypt

Complete guide for securely managing secrets in the BaliBlissed backend using git-crypt.

## Table of Contents

- [Overview](#overview)
- [Installation](#installation)
- [Initial Setup](#initial-setup)
- [Configuration](#configuration)
- [Daily Workflow](#daily-workflow)
- [Team Collaboration](#team-collaboration)
- [Backup and Recovery](#backup-and-recovery)
- [Troubleshooting](#troubleshooting)
- [Best Practices](#best-practices)

## Overview

git-crypt provides **transparent encryption** for files in Git repositories. Files are automatically encrypted when committed and decrypted when checked out by authorized users.

### How It Works

```text
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Your Editor    │────▶│  Git Commit     │────▶│  GitHub/GitLab  │
│  (Plaintext)    │     │  (Encrypted)    │     │  (Encrypted)    │
└─────────────────┘     └─────────────────┘     └─────────────────┘
       ▲                                               │
       │                                               │
       └───────────────────────────────────────────────┘
                    Git Checkout
                    (Auto-decrypted)
```

### What Gets Encrypted

| File/Directory               | Status            | Reason                          |
| ---------------------------- | ----------------- | ------------------------------- |
| `secrets/.env`               | ✅ Encrypted      | Contains credentials            |
| `secrets/token.json`         | ✅ Encrypted      | OAuth tokens                    |
| `secrets/client_secret.json` | ✅ Encrypted      | API secrets                     |
| `secrets/redis-certs/`       | ⚠️ Optional       | Certificates can be public      |
| `secrets/.env.example`       | ❌ Not encrypted  | Template file                   |
| `.gitattributes`             | ❌ Not encrypted  | Configuration file              |
| `.git-crypt/`                | ❌ Not encrypted  | Key metadata (already encrypted)|

## Installation

### macOS

```bash
brew install git-crypt
```

### Ubuntu/Debian

```bash
sudo apt-get update
sudo apt-get install git-crypt
```

### From Source

```bash
git clone https://github.com/AGWA/git-crypt.git
cd git-crypt
make
sudo make install
```

### Verify Installation

```bash
git-crypt --version
# Output: git-crypt 0.7.0
```

## Initial Setup

### Step 1: Initialize git-crypt

From the project root:

```bash
cd /Users/madesuryawan/Documents/Source_Codes/Web_Dev/Unified_Backend/backend

# Initialize git-crypt in the repository
git-crypt init

# Creates .git-crypt/ directory with encryption keys
```

**What this does:**

- Generates a symmetric encryption key
- Creates `.git-crypt/` directory (tracked by Git)
- Prepares the repository for transparent encryption

### Step 2: Configure .gitattributes

Create `.gitattributes` in the project root:

```bash
# Create .gitattributes file
cat > .gitattributes << 'EOF'
# git-crypt configuration - files matching these patterns are encrypted

# Encrypt all files in secrets/
secrets/** filter=git-crypt diff=git-crypt

# Encrypt sensitive file types
*.key filter=git-crypt diff=git-crypt
*.pem filter=git-crypt diff=git-crypt
*.p12 filter=git-crypt diff=git-crypt
.env filter=git-crypt diff=git-crypt

# Do NOT encrypt these (templates and examples)
secrets/.env.example !filter !diff
secrets/*.example !filter !diff
*.md !filter !diff
*.txt !filter !diff

# Redis certificates are public (optional)
# Uncomment if you don't want to encrypt certs
# secrets/redis-certs/* !filter !diff
EOF
```

**What this does:**

- Tells Git which files to encrypt via git-crypt
- `filter=git-crypt` = encrypt on commit, decrypt on checkout
- `!filter !diff` = explicitly exclude from encryption

### Step 3: Stage Configuration Files

```bash
# Add configuration files
git add .gitattributes
git add .git-crypt/

# Commit (these are safe to commit - no secrets here)
git commit -m "Initialize git-crypt for secrets management"
```

### Step 4: Export Your Key (CRITICAL)

**⚠️ WARNING: Do this immediately after init!**

```bash
# Export the symmetric key for backup
git-crypt export-key ~/git-crypt-backend-$(date +%Y%m%d).key

# Set secure permissions
chmod 600 ~/git-crypt-backend-*.key

# Verify
git-crypt status
```

**Store this key in multiple safe locations:**

- Password manager (1Password, Bitwarden)
- Encrypted USB drive
- Cloud storage (encrypted)
- Team password vault

### Step 5: Add Your Secrets

Now add files that should be encrypted:

```bash
# Method 1: Force-add (recommended - keeps secrets/ in .gitignore)
git add -f secrets/.env
git add -f secrets/token.json
git add -f secrets/client_secret.json

# Method 2: If you restructured directories
git add secrets/encrypted/

# Commit (files will be encrypted automatically)
git commit -m "Add encrypted secrets"
```

**Verification:**

```bash
# Check encryption status
git-crypt status

# View encrypted files in Git
git show HEAD:secrets/.env
# Output: ï¿¿GITCRYPTï¿¿... (encrypted binary)
```

## Configuration

### Repository Structure

After setup, your repository should look like:

```text
backend/
├── .git/                           # Git repository
├── .git-crypt/                     # git-crypt metadata (TRACKED)
│   └── keys/
│       ├── 0/
│       │   └── [GPG key files]
│       └── default                 # Symmetric key (encrypted)
├── .gitattributes                  # Encryption rules (TRACKED)
├── .gitignore                      # Ignore patterns
│   └── secrets/                    # Ignore secrets (force-add encrypted ones)
├── secrets/                        # SECRET FILES
│   ├── .env                        # 🔒 ENCRYPTED - Production credentials
│   ├── .env.example                # 📄 PLAINTEXT - Template
│   ├── token.json                  # 🔒 ENCRYPTED - OAuth token
│   ├── client_secret.json          # 🔒 ENCRYPTED - API credentials
│   └── redis-certs/                # 📄 PLAINTEXT or 🔒 ENCRYPTED
│       ├── ca-cert.pem
│       └── ...
└── docs/
    └── secrets/
        └── SECRETS.md              # This file
```

### File Status Reference

| File                   | Tracked? | Encrypted?          | In .gitignore? |
| ---------------------- | -------- | ------------------- | -------------- |
| `.gitattributes`       | ✅ Yes   | ❌ N/A              | ❌ No          |
| `.git-crypt/`          | ✅ Yes   | ❌ Already encrypted| ❌ No          |
| `secrets/.env`         | ✅ Yes   | ✅ Yes              | ⚠️ Force-add   |
| `secrets/.env.example` | ✅ Yes   | ❌ No               | ❌ No          |
| `git-crypt.key`        | ❌ No    | ❌ N/A              | ✅ Yes         |

## Daily Workflow

### Normal Development

```bash
# 1. Clone repository (if new machine)
git clone https://github.com/yourname/backend.git
cd backend

# 2. Unlock repository
git-crypt unlock ~/git-crypt-backend-20240115.key
# Or if using GPG:
git-crypt unlock

# 3. Edit files normally
nano secrets/.env

# 4. Stage and commit (automatically encrypted)
git add secrets/.env
git commit -m "Update database credentials"
git push

# 5. Lock when done (optional)
git-crypt lock
```

### Checking Status

```bash
# Show all files and their encryption status
git-crypt status

# Show only encrypted files
git-crypt status -e

# Show only unencrypted files
git-crypt status -u
```

### Locking/Unlocking

```bash
# Lock repository (re-encrypt all files)
git-crypt lock

# Unlock with symmetric key
git-crypt unlock ~/path/to/key

# Unlock with GPG (if configured)
git-crypt unlock
```

## Team Collaboration

### Adding Team Members (GPG Method)

**For the repository owner:**

```bash
# Add team member by their GPG key
git-crypt add-gpg-user teammate@company.com

# Commit the new key
git add .git-crypt/
git commit -m "Add access for teammate@company.com"
git push
```

**For the new team member:**

```bash
# 1. Clone repository
git clone https://github.com/yourname/backend.git

# 2. Ensure their GPG key is in their keychain
gpg --list-keys

# 3. Unlock (automatic with GPG)
git-crypt unlock

# 4. Verify
cat secrets/.env  # Should show plaintext
```

### Sharing Symmetric Key (Small Teams)

**Not recommended for large teams** - use GPG method instead.

```bash
# Export key securely
git-crypt export-key /tmp/key-file

# Transfer securely (not via email!)
# - Signal
# - 1Password shared vault
# - In-person USB transfer

# Recipient imports
git-crypt unlock /tmp/key-file
```

### Removing Access

```bash
# Rotate the encryption key (invalidate old keys)
git-crypt rotate-key

# Update all encrypted files
git-crypt status -e | xargs git add
git commit -m "Rotate encryption key"
git push

# Distribute new key to remaining team members
```

## Backup and Recovery

### Backup Your Key

```bash
# Multiple backup locations
KEY_NAME="git-crypt-backend-$(date +%Y%m%d).key"

# 1. Home directory (encrypted macOS drive)
git-crypt export-key ~/$KEY_NAME
chmod 600 ~/$KEY_NAME

# 2. Password manager (1Password, Bitwarden)
# Attach file to secure note

# 3. Encrypted USB drive
cp ~/$KEY_NAME /Volumes/EncryptedUSB/secrets/

# 4. Cloud (encrypted)
gpg --symmetric --cipher-algo AES256 ~/$KEY_NAME
# Upload ~/$KEY_NAME.gpg to cloud
```

### Recovery Scenarios

#### Scenario 1: Lost Key File

**If you have access to an unlocked repository:**

```bash
# On a machine where repo is unlocked
git-crypt export-key ~/new-key.key
# Securely transfer to new location
```

**If no unlocked copies exist:**

```bash
# Data is permanently lost
# Restore secrets from other backups (password manager, etc.)
# Re-initialize git-crypt with new key
# Re-add all secrets
```

#### Scenario 2: New Machine Setup

```bash
# 1. Clone repository
git clone https://github.com/yourname/backend.git

# 2. Retrieve key from password manager
# Download to: ~/git-crypt-backend.key

# 3. Unlock
git-crypt unlock ~/git-crypt-backend.key

# 4. Verify
cat secrets/.env  # Should show plaintext
```

#### Scenario 3: Compromised Key

```bash
# 1. Rotate encryption key immediately
git-crypt rotate-key

# 2. Re-commit all encrypted files
git add secrets/
git commit -m "Security: Rotate encryption key after compromise"
git push

# 3. Generate and distribute new key
git-crypt export-key ~/git-crypt-backend-new.key
# Securely share with team

# 4. Revoke old key everywhere
rm ~/git-crypt-backend-old.key
# Remove from password managers
# Remove from cloud storage
```

## Troubleshooting

### Issue: "this repository is not configured for git-crypt"

**Cause:** `.git-crypt/` directory is missing or corrupted.

**Solution:**

```bash
# Check if .git-crypt exists
ls -la .git-crypt/

# If missing, restore from Git
git checkout HEAD -- .git-crypt/

# Verify
git-crypt status
```

### Issue: Files appear encrypted after pull

**Cause:** Repository is locked or key not available.

**Solution:**

```bash
# Unlock with your key
git-crypt unlock ~/path/to/your/key

# Or with GPG
git-crypt unlock
```

### Issue: "git-crypt: error: encrypted file has been tampered with"

**Cause:** File was modified without proper encryption.

**Solution:**

```bash
# Restore from Git
git checkout HEAD -- secrets/tampered-file

# Verify
git-crypt status
```

### Issue: Cannot add new secret files

**Cause:** `.gitignore` is blocking the files.

**Solution:**

```bash
# Force-add the file
git add -f secrets/new-secret.txt

# Verify it's encrypted in the commit
git show HEAD:secrets/new-secret.txt
```

### Issue: Accidentally committed unencrypted secrets

**URGENT:**

```bash
# 1. Immediately rotate key
git-crypt rotate-key

# 2. Remove sensitive data from Git history
# Option A: Filter-branch (rewrites history)
git filter-branch --force --index-filter \
  'git rm --cached --ignore-unmatch secrets/.env' \
  HEAD

# Option B: BFG Repo-Cleaner (faster for large repos)
bfg --delete-files secrets/.env

# 3. Force push (coordinate with team!)
git push --force

# 4. Invalidate exposed credentials immediately!
# - Rotate passwords
# - Revoke tokens
# - Generate new API keys
```

## Best Practices

### DO ✅

- **Export and backup your key immediately** after initialization
- **Store key in multiple secure locations** (password manager + encrypted USB)
- **Use GPG keys for teams** instead of shared symmetric keys
- **Rotate keys periodically** (quarterly) or when team members leave
- **Keep `.env.example` unencrypted** as a template
- **Document which files are encrypted** in your README
- **Test unlock on fresh clones** to verify setup works

### DON'T ❌

- **Never commit `git-crypt export-key` file** to Git
- **Never email or Slack the key**
- **Don't lose your key** - no backdoor exists
- **Don't modify encrypted files directly in GitHub web UI**
- **Don't assume all files in `secrets/` are encrypted** - verify with `git-crypt status`

### Security Checklist

- [ ] Key exported and stored in password manager
- [ ] Key backed up to encrypted USB drive
- [ ] Team members have GPG keys configured (for team repos)
- [ ] `.gitattributes` properly configured
- [ ] `secrets/.env.example` is unencrypted (template)
- [ ] Verified encryption with `git-crypt status`
- [ ] Tested fresh clone and unlock process
- [ ] Documented key recovery process

## Migration from .gitignore to git-crypt

If you currently have secrets in `.gitignore` and want to migrate:

```bash
# 1. Initialize git-crypt
git-crypt init

# 2. Configure .gitattributes
echo "secrets/** filter=git-crypt diff=git-crypt" >> .gitattributes
echo "secrets/.env.example !filter !diff" >> .gitattributes

# 3. Export key
git-crypt export-key ~/git-crypt-backend.key

# 4. Force-add your secrets (they're currently ignored)
git add -f secrets/.env
git add -f secrets/token.json
git add -f secrets/client_secret.json

# 5. Commit everything
git add .gitattributes .git-crypt/
git commit -m "Migrate secrets to git-crypt"

# 6. Verify
git-crypt status
git show HEAD:secrets/.env | head -1  # Should show "GITCRYPT"
```

## Comparison with Alternatives

| Tool           | Encryption | Best For          | When to Choose                      |
| -------------- | ---------- | ----------------- | ----------------------------------- |
| **git-crypt**  | Transparent| Daily workflow    | You want normal git ops             |
| **git-secret** | Manual GPG | Selective sharing | Only specific people need access    |
| **SOPS**       | YAML/JSON  | Cloud configs     | AWS/GCP KMS integration             |
| **BlackBox**   | GPG        | Complex setups    | Multiple file types, large teams    |
| **Age**        | Modern     | Simple encryption | You want modern crypto, small teams |

### When to Use git-crypt

✅ **Choose git-crypt when:**

- You want transparent encryption (no manual steps)
- Team already uses GPG
- You encrypt entire directories
- You want minimal workflow disruption

❌ **Don't use git-crypt when:**

- You need per-file access control (use git-secret)
- You're managing Kubernetes secrets (use SOPS)
- You need audit logging (use HSM or cloud KMS)

## Additional Resources

- [git-crypt GitHub](https://github.com/AGWA/git-crypt)
- [Git Attributes Documentation](https://git-scm.com/docs/gitattributes)
- [GPG Key Management](https://gnupg.org/gph/en/manual/c235.html)
- [Mozilla SOPS](https://github.com/getsops/sops) (alternative)

## Quick Reference Card

```bash
# Setup
git-crypt init
git-crypt export-key ~/backup.key

# Daily use
git-crypt status          # Check encryption
git-crypt unlock          # Decrypt files
git add -f secrets/file   # Add new secret
git-crypt lock            # Re-encrypt

# Team
git-crypt add-gpg-user user@email.com
git-crypt rotate-key      # Rotate keys

# Emergency
git-crypt unlock ~/backup.key   # Restore access
```

---

**Remember:** Your encryption key is the only way to access your secrets. Guard it carefully!

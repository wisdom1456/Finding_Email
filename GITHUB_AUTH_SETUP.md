# GitHub Authentication Setup Guide

This guide helps you resolve the Git authentication error and successfully push your code to GitHub.

## Error You're Seeing

```
remote: Invalid username or token. Password authentication is not supported for Git operations.
fatal: Authentication failed for 'https://github.com/wisdom1456/Finding_Email.git/'
```

## Solution Options

### Option 1: Personal Access Token (PAT) - Recommended

This is the easiest method for HTTPS authentication.

#### Step 1: Create a Personal Access Token

1. Go to GitHub: https://github.com/settings/tokens
2. Click **"Generate new token"** → **"Generate new token (classic)"**
3. Give it a descriptive name: `Legal Portal Development`
4. Select scopes:
   - ✅ `repo` (Full control of private repositories)
   - ✅ `workflow` (if using GitHub Actions)
5. Click **"Generate token"**
6. **IMPORTANT**: Copy the token immediately (you won't see it again!)

#### Step 2: Use the Token to Push

```bash
# First time - Git will prompt for credentials
git push origin tool-fork-development

# When prompted:
# Username: wisdom1456
# Password: [paste your token here, NOT your GitHub password]

# OR use this one-liner to push with token directly:
git remote set-url origin https://YOUR_TOKEN@github.com/wisdom1456/Finding_Email.git
git push origin tool-fork-development
```

#### Step 3: Cache Credentials (Optional)

To avoid entering the token every time:

**macOS:**
```bash
git config --global credential.helper osxkeychain
```

**Windows:**
```bash
git config --global credential.helper manager
```

**Linux:**
```bash
git config --global credential.helper cache
# Or for permanent storage:
git config --global credential.helper store
```

---

### Option 2: SSH Keys - Most Secure

This method uses SSH keys instead of passwords/tokens.

#### Step 1: Generate SSH Key

```bash
# Generate new SSH key
ssh-keygen -t ed25519 -C "your-email@example.com"

# When prompted, press Enter to accept default location
# Optionally set a passphrase (recommended)

# Start SSH agent
eval "$(ssh-agent -s)"

# Add key to SSH agent
ssh-add ~/.ssh/id_ed25519
```

#### Step 2: Add SSH Key to GitHub

```bash
# Copy your public key
cat ~/.ssh/id_ed25519.pub

# Or on macOS:
pbcopy < ~/.ssh/id_ed25519.pub
```

1. Go to GitHub: https://github.com/settings/keys
2. Click **"New SSH key"**
3. Title: `Legal Portal Development Machine`
4. Paste the public key
5. Click **"Add SSH key"**

#### Step 3: Test SSH Connection

```bash
# Test connection
ssh -T git@github.com

# You should see:
# Hi wisdom1456! You've successfully authenticated...
```

#### Step 4: Update Git Remote to Use SSH

```bash
# Change remote URL from HTTPS to SSH
git remote set-url origin git@github.com:wisdom1456/Finding_Email.git

# Verify
git remote -v

# Now push
git push origin tool-fork-development
```

---

### Option 3: GitHub CLI (gh)

Modern and convenient method using GitHub's official CLI.

#### Step 1: Install GitHub CLI

**macOS:**
```bash
brew install gh
```

**Windows:**
```
Download from: https://cli.github.com/
```

**Linux:**
```bash
# Debian/Ubuntu
curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
sudo apt update
sudo apt install gh
```

#### Step 2: Authenticate

```bash
# Login to GitHub
gh auth login

# Follow the prompts:
# ? What account do you want to log into? GitHub.com
# ? What is your preferred protocol for Git operations? HTTPS
# ? Authenticate Git with your GitHub credentials? Yes
# ? How would you like to authenticate? Login with a web browser
```

#### Step 3: Push

```bash
git push origin tool-fork-development
```

---

## Quick Fix Script

Save this as `fix_git_auth.sh` and run it:

```bash
#!/bin/bash

echo "GitHub Authentication Fix"
echo "========================="
echo ""
echo "Choose authentication method:"
echo "1) Personal Access Token (PAT)"
echo "2) SSH Keys"
echo "3) GitHub CLI (gh)"
echo ""
read -p "Enter choice [1-3]: " choice

case $choice in
    1)
        echo ""
        echo "1. Create token: https://github.com/settings/tokens"
        echo "2. Select 'repo' scope"
        echo "3. Copy the token"
        echo ""
        read -p "Enter your Personal Access Token: " token
        
        if [ ! -z "$token" ]; then
            git remote set-url origin https://$token@github.com/wisdom1456/Finding_Email.git
            echo "✅ Remote URL updated with token"
            echo "Attempting to push..."
            git push origin tool-fork-development
        else
            echo "❌ Token cannot be empty"
        fi
        ;;
    
    2)
        echo ""
        echo "Checking for existing SSH keys..."
        
        if [ -f ~/.ssh/id_ed25519.pub ]; then
            echo "✅ SSH key found"
            echo "Your public key:"
            cat ~/.ssh/id_ed25519.pub
            echo ""
            echo "Add this key to GitHub: https://github.com/settings/keys"
        else
            echo "No SSH key found. Generating one..."
            ssh-keygen -t ed25519 -C "legal-portal@github.com"
            eval "$(ssh-agent -s)"
            ssh-add ~/.ssh/id_ed25519
            echo ""
            echo "Your new public key:"
            cat ~/.ssh/id_ed25519.pub
            echo ""
            echo "Add this key to GitHub: https://github.com/settings/keys"
        fi
        
        read -p "Press Enter after adding key to GitHub..."
        
        # Test connection
        ssh -T git@github.com
        
        # Update remote
        git remote set-url origin git@github.com:wisdom1456/Finding_Email.git
        echo "✅ Remote URL updated to use SSH"
        echo "Attempting to push..."
        git push origin tool-fork-development
        ;;
    
    3)
        echo ""
        if command -v gh &> /dev/null; then
            echo "GitHub CLI found. Logging in..."
            gh auth login
            echo "Attempting to push..."
            git push origin tool-fork-development
        else
            echo "❌ GitHub CLI not installed"
            echo "Install it from: https://cli.github.com/"
            echo ""
            echo "macOS: brew install gh"
            echo "Windows: Download from website"
            echo "Linux: See https://github.com/cli/cli/blob/trunk/docs/install_linux.md"
        fi
        ;;
    
    *)
        echo "Invalid choice"
        ;;
esac
```

Make it executable and run:
```bash
chmod +x fix_git_auth.sh
./fix_git_auth.sh
```

---

## Verification

After setting up authentication, verify it works:

```bash
# Check remote URL
git remote -v

# Try to push
git push origin tool-fork-development

# If successful, you should see:
# Enumerating objects: ...
# Counting objects: ...
# Writing objects: ...
# Total X (delta Y), reused 0 (delta 0)
# To github.com:wisdom1456/Finding_Email.git
#    abc1234..def5678  tool-fork-development -> tool-fork-development
```

---

## Troubleshooting

### "Permission denied (publickey)"
- Your SSH key isn't added to GitHub
- Follow Option 2 steps again

### "Invalid username or password"
- You're using your GitHub password instead of a PAT
- Create a new PAT following Option 1

### "Repository not found"
- Check repository name: `wisdom1456/Finding_Email`
- Verify you have access to the repository
- Make sure you're authenticated as the correct user

### Token/SSH key not persisting
- Set up credential helper (see Option 1, Step 3)
- For SSH, ensure ssh-agent is running

---

## Security Best Practices

1. **Never commit tokens/keys to Git**
   ```bash
   # Add to .gitignore
   echo ".env" >> .gitignore
   echo "*.pem" >> .gitignore
   echo "*.key" >> .gitignore
   ```

2. **Use tokens with minimal scopes**
   - Only enable `repo` if that's all you need
   - Create separate tokens for different purposes

3. **Set token expiration**
   - Use 90-day expiration for security
   - Set calendar reminder to regenerate

4. **Protect your SSH private key**
   ```bash
   chmod 600 ~/.ssh/id_ed25519
   ```

5. **Use passphrase for SSH keys**
   - Adds extra security layer
   - Use ssh-agent to avoid re-entering constantly

---

## Next Steps

After successfully pushing:

```bash
# Verify your changes are on GitHub
gh repo view wisdom1456/Finding_Email --web

# Or visit directly:
# https://github.com/wisdom1456/Finding_Email/tree/tool-fork-development

# Create a pull request to merge to main
gh pr create --title "Major improvements - GPT-4o Vision migration" \
             --body "See commit message for details"
```

---

**Need Help?**
- GitHub Docs: https://docs.github.com/en/authentication
- SSH Troubleshooting: https://docs.github.com/en/authentication/troubleshooting-ssh
- PAT Guide: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/creating-a-personal-access-token


#!/bin/bash
# Interactive Setup and Deployment Script for Legal Portal
# This script guides you through Git authentication and Google Cloud deployment

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Banner
echo -e "${GREEN}"
echo "╔════════════════════════════════════════════════════════╗"
echo "║     Legal Portal - Setup & Deployment Wizard         ║"
echo "╚════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Function to print status
print_status() {
    echo -e "${BLUE}➜${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

# Check if git is installed
if ! command -v git &> /dev/null; then
    print_error "Git is not installed. Please install Git first."
    exit 1
fi

print_success "Git found"

# Main menu
echo ""
echo "What would you like to do?"
echo ""
echo "1) Fix GitHub Authentication & Push Code"
echo "2) Deploy to Google Cloud"
echo "3) Both (recommended)"
echo "4) Test Locally with Docker"
echo "5) Exit"
echo ""
read -p "Enter choice [1-5]: " main_choice

case $main_choice in
    1|3)
        echo ""
        echo -e "${YELLOW}════════════════════════════════════════${NC}"
        echo -e "${YELLOW}    GitHub Authentication Setup${NC}"
        echo -e "${YELLOW}════════════════════════════════════════${NC}"
        echo ""
        
        echo "Choose authentication method:"
        echo ""
        echo "1) Personal Access Token (PAT) - Easiest"
        echo "2) SSH Key - Most Secure"
        echo "3) GitHub CLI - Most Convenient"
        echo ""
        read -p "Enter choice [1-3]: " auth_choice
        
        case $auth_choice in
            1)
                echo ""
                print_status "Setting up Personal Access Token authentication..."
                echo ""
                echo "Steps:"
                echo "1. Open this URL in your browser: ${BLUE}https://github.com/settings/tokens${NC}"
                echo "2. Click 'Generate new token' → 'Generate new token (classic)'"
                echo "3. Give it a name: 'Legal Portal Development'"
                echo "4. Select scope: ✓ repo"
                echo "5. Click 'Generate token'"
                echo "6. Copy the token (you won't see it again!)"
                echo ""
                read -p "Press Enter to open GitHub in browser (or skip and enter token)..."
                
                # Try to open browser
                if command -v open &> /dev/null; then
                    open "https://github.com/settings/tokens"
                elif command -v xdg-open &> /dev/null; then
                    xdg-open "https://github.com/settings/tokens"
                fi
                
                echo ""
                read -sp "Paste your Personal Access Token: " token
                echo ""
                
                if [ -z "$token" ]; then
                    print_error "Token cannot be empty"
                    exit 1
                fi
                
                print_status "Updating Git remote URL..."
                git remote set-url origin "https://${token}@github.com/wisdom1456/Finding_Email.git"
                print_success "Remote URL updated"
                
                print_status "Configuring credential helper..."
                if [[ "$OSTYPE" == "darwin"* ]]; then
                    git config --global credential.helper osxkeychain
                elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
                    git config --global credential.helper cache
                fi
                print_success "Credential helper configured"
                ;;
            
            2)
                echo ""
                print_status "Setting up SSH key authentication..."
                echo ""
                
                if [ -f ~/.ssh/id_ed25519.pub ]; then
                    print_success "SSH key already exists"
                    echo ""
                    echo "Your public key:"
                    cat ~/.ssh/id_ed25519.pub
                else
                    print_status "Generating new SSH key..."
                    read -p "Enter your email: " email
                    ssh-keygen -t ed25519 -C "$email"
                    eval "$(ssh-agent -s)"
                    ssh-add ~/.ssh/id_ed25519
                    print_success "SSH key generated"
                    echo ""
                    echo "Your public key:"
                    cat ~/.ssh/id_ed25519.pub
                fi
                
                echo ""
                echo "Steps:"
                echo "1. Copy the public key above"
                echo "2. Open: ${BLUE}https://github.com/settings/keys${NC}"
                echo "3. Click 'New SSH key'"
                echo "4. Paste the key and save"
                echo ""
                read -p "Press Enter after adding key to GitHub..."
                
                # Try to open browser
                if command -v open &> /dev/null; then
                    open "https://github.com/settings/keys"
                elif command -v xdg-open &> /dev/null; then
                    xdg-open "https://github.com/settings/keys"
                fi
                
                print_status "Testing SSH connection..."
                if ssh -T git@github.com 2>&1 | grep -q "successfully authenticated"; then
                    print_success "SSH authentication successful"
                else
                    print_warning "SSH test inconclusive, but continuing..."
                fi
                
                print_status "Updating Git remote to use SSH..."
                git remote set-url origin "git@github.com:wisdom1456/Finding_Email.git"
                print_success "Remote URL updated"
                ;;
            
            3)
                echo ""
                print_status "Setting up GitHub CLI authentication..."
                echo ""
                
                if ! command -v gh &> /dev/null; then
                    print_error "GitHub CLI is not installed"
                    echo ""
                    echo "Install it:"
                    echo "  macOS:   brew install gh"
                    echo "  Windows: Download from https://cli.github.com/"
                    echo "  Linux:   See https://github.com/cli/cli#installation"
                    exit 1
                fi
                
                print_success "GitHub CLI found"
                print_status "Authenticating with GitHub..."
                gh auth login
                print_success "Authentication complete"
                ;;
            
            *)
                print_error "Invalid choice"
                exit 1
                ;;
        esac
        
        # Push to GitHub
        echo ""
        print_status "Pushing code to GitHub..."
        if git push origin tool-fork-development; then
            print_success "Code successfully pushed to GitHub!"
        else
            print_error "Failed to push code"
            echo ""
            echo "Troubleshooting:"
            echo "1. Check your token/SSH key is correct"
            echo "2. Verify you have write access to the repository"
            echo "3. See GITHUB_AUTH_SETUP.md for more help"
            exit 1
        fi
        
        if [ "$main_choice" != "3" ]; then
            echo ""
            print_success "GitHub setup complete!"
            exit 0
        fi
        ;;
esac

case $main_choice in
    2|3)
        echo ""
        echo -e "${YELLOW}════════════════════════════════════════${NC}"
        echo -e "${YELLOW}    Google Cloud Deployment${NC}"
        echo -e "${YELLOW}════════════════════════════════════════${NC}"
        echo ""
        
        # Check for gcloud
        if ! command -v gcloud &> /dev/null; then
            print_error "Google Cloud SDK is not installed"
            echo ""
            echo "Install it:"
            echo "  macOS:   brew install google-cloud-sdk"
            echo "  Windows: https://cloud.google.com/sdk/docs/install"
            echo "  Linux:   https://cloud.google.com/sdk/docs/install"
            exit 1
        fi
        
        print_success "Google Cloud SDK found"
        
        # Check authentication
        if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" &> /dev/null; then
            print_warning "Not logged into Google Cloud"
            print_status "Running authentication..."
            gcloud auth login
        fi
        
        print_success "Authenticated with Google Cloud"
        
        # Get project ID
        if [ -z "$GOOGLE_CLOUD_PROJECT" ]; then
            echo ""
            read -p "Enter your Google Cloud Project ID: " project_id
            export GOOGLE_CLOUD_PROJECT="$project_id"
        else
            print_status "Using project: $GOOGLE_CLOUD_PROJECT"
        fi
        
        # Get region
        if [ -z "$GOOGLE_CLOUD_REGION" ]; then
            export GOOGLE_CLOUD_REGION="us-central1"
        fi
        print_status "Using region: $GOOGLE_CLOUD_REGION"
        
        # Confirm
        echo ""
        echo "Deployment Configuration:"
        echo "  Project: $GOOGLE_CLOUD_PROJECT"
        echo "  Region:  $GOOGLE_CLOUD_REGION"
        echo "  Service: legal-portal"
        echo ""
        read -p "Continue with deployment? [y/N]: " confirm
        
        if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
            print_warning "Deployment cancelled"
            exit 0
        fi
        
        # Run deployment script
        print_status "Starting deployment..."
        if [ -f "./deploy.sh" ]; then
            bash ./deploy.sh
        else
            print_error "deploy.sh not found in current directory"
            exit 1
        fi
        
        print_success "Deployment complete!"
        ;;
    
    4)
        echo ""
        echo -e "${YELLOW}════════════════════════════════════════${NC}"
        echo -e "${YELLOW}    Local Docker Test${NC}"
        echo -e "${YELLOW}════════════════════════════════════════${NC}"
        echo ""
        
        # Check for Docker
        if ! command -v docker &> /dev/null; then
            print_error "Docker is not installed"
            echo "Install from: https://docs.docker.com/get-docker/"
            exit 1
        fi
        
        print_success "Docker found"
        
        # Get API keys
        echo ""
        print_status "Environment Configuration"
        read -p "OpenAI API Key: " openai_key
        read -p "Google Cloud Project ID: " gcp_project
        
        # Build
        print_status "Building Docker image..."
        docker build -t legal-portal:test .
        print_success "Image built"
        
        # Run
        print_status "Starting container on port 8080..."
        docker run -p 8080:8080 \
            -e OPENAI_API_KEY="$openai_key" \
            -e GOOGLE_CLOUD_PROJECT="$gcp_project" \
            -e ENVIRONMENT="development" \
            legal-portal:test &
        
        CONTAINER_PID=$!
        
        echo ""
        print_success "Container started!"
        echo ""
        echo "Access the application at: ${BLUE}http://localhost:8080${NC}"
        echo ""
        echo "Press Ctrl+C to stop the container"
        
        # Wait for interrupt
        trap "kill $CONTAINER_PID 2>/dev/null; print_warning 'Container stopped'; exit 0" INT
        wait $CONTAINER_PID
        ;;
    
    5)
        print_status "Exiting..."
        exit 0
        ;;
    
    *)
        print_error "Invalid choice"
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}"
echo "╔════════════════════════════════════════════════════════╗"
echo "║              All Steps Complete! 🎉                   ║"
echo "╚════════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo ""
echo "Next steps:"
echo "• View logs: gcloud run services logs tail legal-portal"
echo "• Update service: ./deploy.sh"
echo "• See full docs: cat DEPLOYMENT_GUIDE.md"
echo ""


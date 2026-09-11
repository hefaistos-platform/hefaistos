#!/bin/bash

# =============================================================================
# HEFAISTOS UFW FIREWALL CONFIGURATION HELPER
# =============================================================================
# Purpose: Safely configure Ubuntu UFW firewall for Hefaistos deployment
# Usage: ./setup-firewall.sh [--domain example.com] [--disable]
# Requires: root access (sudo)
# =============================================================================

set -e

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
DOMAIN="${1:-}"
ACTION="${2:-enable}"
LOG_FILE="/var/log/hefaistos-firewall-$(date '+%Y%m%d_%H%M%S').log"

# Logging functions
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

log_success() {
    echo -e "${GREEN}✓${NC} $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo -e "${RED}✗ ERROR:${NC} $1" | tee -a "$LOG_FILE"
}

log_warning() {
    echo -e "${YELLOW}⚠ WARNING:${NC} $1" | tee -a "$LOG_FILE"
}

# Check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root (use sudo)"
        exit 1
    fi
    log_success "Running as root"
}

# Install UFW if not present
install_ufw() {
    if ! command -v ufw &> /dev/null; then
        log "Installing UFW firewall..."
        apt-get update -qq
        apt-get install -y -qq ufw
        log_success "UFW installed"
    else
        log_success "UFW already installed"
    fi
}

# Configure firewall
configure_firewall() {
    log "Configuring UFW firewall..."
    
    # Enable UFW
    ufw --force enable 2>&1 | tee -a "$LOG_FILE"
    log_success "UFW enabled"
    
    # Set default policies (secure by default)
    ufw default deny incoming 2>&1 | tee -a "$LOG_FILE"
    ufw default allow outgoing 2>&1 | tee -a "$LOG_FILE"
    log_success "Default policies: deny incoming, allow outgoing"
    
    # Allow SSH (critical!)
    log "Allowing SSH access (port 22)..."
    ufw allow 22/tcp comment "SSH Access" 2>&1 | tee -a "$LOG_FILE"
    log_success "SSH allowed (port 22) - CRITICAL for remote access"
    
    # Allow HTTP/HTTPS
    log "Allowing HTTP/HTTPS traffic..."
    ufw allow 80/tcp comment "HTTP" 2>&1 | tee -a "$LOG_FILE"
    ufw allow 443/tcp comment "HTTPS" 2>&1 | tee -a "$LOG_FILE"
    log_success "HTTP (80) and HTTPS (443) allowed"
    
    # Allow backend API (if not behind nginx proxy)
    log "Allowing backend API access..."
    ufw allow 8000/tcp comment "Backend API" 2>&1 | tee -a "$LOG_FILE"
    log_success "Backend API (8000) allowed"
    
    # Optional: Allow from specific networks
    # These are common private networks
    log "Allowing private network access..."
    ufw allow from 192.168.0.0/16 comment "Private 192.168.x.x" 2>&1 | tee -a "$LOG_FILE"
    ufw allow from 10.0.0.0/8 comment "Private 10.x.x.x" 2>&1 | tee -a "$LOG_FILE"
    ufw allow from 172.16.0.0/12 comment "Private 172.16-31.x.x" 2>&1 | tee -a "$LOG_FILE"
    log_success "Private network access allowed"
    
    # Optional: Docker container access
    log "Allowing Docker bridge network..."
    ufw allow from 172.17.0.0/16 comment "Docker bridge" 2>&1 | tee -a "$LOG_FILE"
    log_success "Docker bridge access allowed"
}

# List firewall rules
list_rules() {
    echo ""
    log "Current firewall rules:"
    echo ""
    ufw status numbered | tee -a "$LOG_FILE"
    echo ""
}

# Disable firewall
disable_firewall() {
    log_warning "Disabling UFW firewall..."
    
    read -p "Are you sure you want to disable the firewall? (yes/no) " -r confirm
    echo
    if [[ ! $confirm =~ ^yes$ ]]; then
        log "Firewall disable cancelled"
        return 0
    fi
    
    ufw disable 2>&1 | tee -a "$LOG_FILE"
    log_success "Firewall disabled"
}

# Allow specific IP
allow_ip() {
    local ip="$1"
    local comment="${2:-Custom IP}"
    
    if [ -z "$ip" ]; then
        read -p "Enter IP address or network (e.g., 192.168.1.0/24): " ip
    fi
    
    if [ -z "$ip" ]; then
        log_error "No IP provided"
        return 1
    fi
    
    log "Adding firewall rule for: $ip"
    ufw allow from "$ip" comment "$comment" 2>&1 | tee -a "$LOG_FILE"
    log_success "Rule added: $ip"
}

# Delete specific rule
delete_rule() {
    list_rules
    
    read -p "Enter rule number to delete (e.g., 5): " rule_num
    
    if [ -z "$rule_num" ]; then
        log_error "No rule number provided"
        return 1
    fi
    
    log_warning "Deleting rule $rule_num..."
    ufw delete "$rule_num" --force 2>&1 | tee -a "$LOG_FILE"
    log_success "Rule deleted"
    
    list_rules
}

# Advanced configuration menu
advanced_menu() {
    while true; do
        echo ""
        echo "╔════════════════════════════════════════════════════════════════╗"
        echo "║        HEFAISTOS FIREWALL - ADVANCED OPTIONS                  ║"
        echo "╚════════════════════════════════════════════════════════════════╝"
        echo ""
        echo "1) Allow specific IP/network"
        echo "2) Delete existing rule"
        echo "3) List all rules"
        echo "4) Reset firewall to defaults"
        echo "5) Return to main menu"
        echo ""
        
        read -p "Choose option (1-5): " choice
        
        case $choice in
            1)
                allow_ip
                ;;
            2)
                delete_rule
                ;;
            3)
                list_rules
                ;;
            4)
                log_warning "Resetting firewall to defaults..."
                read -p "Confirm reset? (yes/no) " confirm
                if [[ $confirm =~ ^yes$ ]]; then
                    ufw reset --force 2>&1 | tee -a "$LOG_FILE"
                    configure_firewall
                    log_success "Firewall reset to defaults"
                fi
                ;;
            5)
                return 0
                ;;
            *)
                log_error "Invalid option"
                ;;
        esac
    done
}

# Main menu
main_menu() {
    while true; do
        echo ""
        echo "╔════════════════════════════════════════════════════════════════╗"
        echo "║        HEFAISTOS UFW FIREWALL CONFIGURATION                    ║"
        echo "╚════════════════════════════════════════════════════════════════╝"
        echo ""
        
        # Check current status
        UFW_STATUS=$(ufw status | grep -o "Status: .*")
        echo "Current status: $UFW_STATUS"
        echo ""
        
        echo "1) Enable and configure firewall (recommended)"
        echo "2) Configure existing firewall"
        echo "3) View current rules"
        echo "4) Advanced options"
        echo "5) Disable firewall"
        echo "6) Exit"
        echo ""
        
        read -p "Choose option (1-6): " choice
        
        case $choice in
            1)
                install_ufw
                configure_firewall
                list_rules
                log_success "Firewall setup completed"
                ;;
            2)
                configure_firewall
                list_rules
                ;;
            3)
                list_rules
                ;;
            4)
                advanced_menu
                ;;
            5)
                disable_firewall
                ;;
            6)
                log "Exiting firewall configuration"
                return 0
                ;;
            *)
                log_error "Invalid option"
                ;;
        esac
    done
}

# Main execution
main() {
    clear
    
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║        HEFAISTOS UFW FIREWALL CONFIGURATION                    ║"
    echo "║        Ubuntu Firewall Helper for Hefaistos Platform          ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""
    
    log "Hefaistos Firewall Configuration Started"
    log "Log file: $LOG_FILE"
    
    check_root
    install_ufw
    
    # If action is "disable"
    if [ "$ACTION" = "disable" ]; then
        disable_firewall
        exit 0
    fi
    
    # Interactive menu
    main_menu
    
    echo ""
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo -e "║  ${GREEN}✓ FIREWALL CONFIGURATION COMPLETE${NC}                           ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""
    log_success "Configuration complete"
    log "Log file saved to: $LOG_FILE"
    echo ""
}

# Execute main function
main "$@"

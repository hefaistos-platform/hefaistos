#!/bin/bash

# =============================================================================
# HEFAISTOS UNINSTALL & ROLLBACK SCRIPT
# =============================================================================
# Purpose: Safe removal of Hefaistos installation with backup preservation
# Usage: ./uninstall-hefaistos.sh [--keep-data] [--keep-backups]
# Options:
#   --keep-data      Keep database and media files (default: remove)
#   --keep-backups   Keep backup files in /backups (default: remove)
#   --full-cleanup   Remove everything including Docker images
# =============================================================================

set -e

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
HEFAISTOS_DIR="${1:-.}"
KEEP_DATA=0
KEEP_BACKUPS=0
FULL_CLEANUP=0
TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
LOG_FILE="${HEFAISTOS_DIR}/uninstall_${TIMESTAMP}.log"

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

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --keep-data)
            KEEP_DATA=1
            log_warning "Will keep database and media files"
            shift
            ;;
        --keep-backups)
            KEEP_BACKUPS=1
            log_warning "Will keep backup files"
            shift
            ;;
        --full-cleanup)
            FULL_CLEANUP=1
            log_warning "Will remove Docker images and volumes"
            shift
            ;;
        *)
            HEFAISTOS_DIR=$1
            shift
            ;;
    esac
done

# Safety check
main() {
    echo ""
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║        HEFAISTOS UNINSTALL & ROLLBACK SCRIPT                   ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""
    
    log "Installation directory: $HEFAISTOS_DIR"
    log "Keep database: $([ $KEEP_DATA -eq 1 ] && echo 'YES' || echo 'NO')"
    log "Keep backups: $([ $KEEP_BACKUPS -eq 1 ] && echo 'YES' || echo 'NO')"
    log "Full cleanup: $([ $FULL_CLEANUP -eq 1 ] && echo 'YES' || echo 'NO')"
    echo ""
    
    # Ask for confirmation
    echo -e "${YELLOW}WARNING: This will remove the Hefaistos installation!${NC}"
    echo "Data preservation:"
    echo "  - Database: $([ $KEEP_DATA -eq 1 ] && echo 'PRESERVED ✓' || echo 'DELETED ✗')"
    echo "  - Media files: $([ $KEEP_DATA -eq 1 ] && echo 'PRESERVED ✓' || echo 'DELETED ✗')"
    echo "  - Backups: $([ $KEEP_BACKUPS -eq 1 ] && echo 'PRESERVED ✓' || echo 'DELETED ✗')"
    echo "  - Docker images: $([ $FULL_CLEANUP -eq 1 ] && echo 'DELETED ✗' || echo 'PRESERVED ✓')"
    echo ""
    
    read -p "Type 'yes' to proceed with uninstall: " -r confirm
    if [ "$confirm" != "yes" ]; then
        log "Uninstall cancelled"
        exit 0
    fi
    echo ""
    
    # Change to hefaistos directory
    if [ ! -d "$HEFAISTOS_DIR" ]; then
        log_error "Directory not found: $HEFAISTOS_DIR"
        exit 1
    fi
    cd "$HEFAISTOS_DIR"
    
    # Stop and remove containers
    log "Stopping Docker containers..."
    if [ -f "docker-compose.yml" ]; then
        if docker-compose down 2>&1 | tee -a "$LOG_FILE"; then
            log_success "Containers stopped"
        else
            log_warning "Could not stop all containers"
        fi
    fi
    echo ""
    
    # Remove volumes (if full cleanup)
    if [ $FULL_CLEANUP -eq 1 ]; then
        log "Removing Docker volumes..."
        if docker-compose down -v 2>&1 | tee -a "$LOG_FILE"; then
            log_success "Volumes removed"
        else
            log_warning "Could not remove all volumes"
        fi
        echo ""
    fi
    
    # Backup database if requested (even if keeping data)
    if [ -f "docker-compose.yml" ]; then
        log "Creating final database backup before uninstall..."
        FINAL_BACKUP="${HEFAISTOS_DIR}/backups/final_backup_${TIMESTAMP}.sql.gz"
        mkdir -p "$(dirname "$FINAL_BACKUP")"
        
        if docker-compose exec -T db pg_dump -U hefaistos_user hefaistos_db 2>/dev/null | gzip > "$FINAL_BACKUP"; then
            BACKUP_SIZE=$(du -h "$FINAL_BACKUP" | awk '{print $1}')
            log_success "Final backup created ($BACKUP_SIZE): $FINAL_BACKUP"
        else
            log_warning "Could not create final backup"
        fi
        echo ""
    fi
    
    # Remove data if not preserving
    if [ $KEEP_DATA -eq 0 ]; then
        log "Removing database and media files..."
        
        rm -rf "$HEFAISTOS_DIR/backend/media" 2>/dev/null || log_warning "Could not remove media directory"
        rm -rf "$HEFAISTOS_DIR/backend/.secrets" 2>/dev/null || log_warning "Could not remove secrets"
        
        log_success "Data files removed"
        echo ""
    else
        log "Preserving database and media files (as requested)"
        echo ""
    fi
    
    # Remove backups if not preserving
    if [ $KEEP_BACKUPS -eq 0 ]; then
        log "Removing backup files..."
        rm -rf "$HEFAISTOS_DIR/backups" 2>/dev/null || log_warning "Could not remove backups"
        log_success "Backups removed"
        echo ""
    else
        log "Preserving backup files (as requested)"
        echo ""
    fi
    
    # Remove Docker images if full cleanup
    if [ $FULL_CLEANUP -eq 1 ]; then
        log "Removing Hefaistos Docker images..."
        docker images | grep hefaistos | awk '{print $3}' | xargs docker rmi -f 2>/dev/null || log_warning "Could not remove all images"
        log_success "Docker images removed"
        echo ""
        
        log "Pruning unused Docker resources..."
        docker system prune -f --all 2>/dev/null || true
        log_success "System cleanup completed"
        echo ""
    fi
    
    # Remove cron job
    log "Removing cron job (if exists)..."
    if crontab -l 2>/dev/null | grep -q "backup-hefaistos.sh"; then
        (crontab -l 2>/dev/null | grep -v "backup-hefaistos.sh" || true) | crontab -
        log_success "Cron job removed"
    else
        log "No cron job found"
    fi
    echo ""
    
    # Remove UFW rules
    log "Checking firewall rules..."
    if command -v ufw &> /dev/null; then
        if ufw status | grep -q "Status: active"; then
            log_warning "UFW firewall is active. Manual cleanup may be required:"
            log_warning "  Review rules: sudo ufw status numbered"
            log_warning "  Remove rule: sudo ufw delete [number]"
        fi
    fi
    echo ""
    
    # Summary
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo -e "║  ${GREEN}✓ UNINSTALL COMPLETED${NC}                                         ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""
    echo "📋 Log file: $LOG_FILE"
    echo ""
    echo "Remaining resources:"
    if [ $KEEP_DATA -eq 1 ]; then
        echo "  ✓ Database backup: $HEFAISTOS_DIR/backups/"
        echo "  ✓ Media files: $HEFAISTOS_DIR/backend/media/"
    fi
    if [ $KEEP_BACKUPS -eq 1 ]; then
        echo "  ✓ Backup files: $HEFAISTOS_DIR/backups/"
    fi
    if [ $FULL_CLEANUP -eq 1 ]; then
        echo "  ✓ All Docker containers, images, and volumes removed"
    fi
    echo ""
    echo "To reinstall:"
    echo "  Follow the manual installation steps in README.md"
    echo "  or clone fresh: git clone https://github.com/hefaistos-platform/hefaistos.git"
    echo ""
    echo "To restore from backup:"
    echo "  gunzip -c final_backup_${TIMESTAMP}.sql.gz | docker-compose exec db psql -U hefaistos_user hefaistos_db"
    echo ""
}

# Run main function
main "$@"

"""
Git utilities for retrieving repository information.
"""
import subprocess
import logging
from typing import Dict, Optional


def get_git_info() -> Dict[str, Optional[str]]:
    """
    Get current git commit hash and date.
    
    Returns:
        Dict containing commit hash, commit date, and branch name.
        Returns None values if git commands fail.
    """
    logger = logging.getLogger(__name__)
    
    git_info = {
        'commit_hash': None,
        'commit_date': None,
        'branch': None
    }
    
    try:
        # Get current commit hash (short version)
        result = subprocess.run(
            ['git', 'rev-parse', '--short', 'HEAD'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            git_info['commit_hash'] = result.stdout.strip()
        
        # Get commit date
        result = subprocess.run(
            ['git', 'show', '-s', '--format=%cd', '--date=format:%Y-%m-%d %H:%M'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            git_info['commit_date'] = result.stdout.strip()
        
        # Get current branch name
        result = subprocess.run(
            ['git', 'branch', '--show-current'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            git_info['branch'] = result.stdout.strip()
            
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        logger.warning(f"Could not retrieve git information: {e}")
    
    return git_info
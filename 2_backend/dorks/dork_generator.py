"""
ReconMind Backend — dorks/dork_generator.py
Dynamic dork generator. Generates search dorks for a target domain.
Phase 5: AI model will enhance/replace this with smarter generation.
"""

from typing import List, Dict


# ─────────────────────────────────────────
# Dork Templates
# {target} will be replaced with the actual domain
# ─────────────────────────────────────────
DORK_TEMPLATES: Dict[str, List[str]] = {

    "file_exposure": [
        'site:{target} ext:sql',
        'site:{target} ext:bak',
        'site:{target} ext:log',
        'site:{target} ext:env',
        'site:{target} ext:dump',
        'site:{target} "index of" "backup"',
        'site:{target} "index of" "uploads"',
        'site:{target} intitle:"index of" "*.gz"',
    ],

    "admin_panels": [
        'site:{target} inurl:admin',
        'site:{target} inurl:login',
        'site:{target} inurl:dashboard',
        'site:{target} inurl:panel',
        'site:{target} inurl:cp',
        'site:{target} intitle:"admin panel"',
        'site:{target} intitle:"login" inurl:admin',
        'site:{target} inurl:wp-admin',
        'site:{target} inurl:administrator',
        'site:{target} inurl:phpmyadmin',
    ],

    "credential_leaks": [
        'site:{target} "password" filetype:txt',
        'site:{target} "api_key" OR "api_secret"',
        'site:{target} "DB_PASSWORD" ext:env',
        'site:{target} "secret_key" ext:cfg',
        'site:{target} "access_token" filetype:json',
        'site:{target} "private_key" ext:pem',
        'site:{target} inurl:config "password"',
        'site:{target} "SMTP_PASSWORD" OR "MAIL_PASSWORD"',
    ],

    "config_files": [
        'site:{target} ext:xml inurl:config',
        'site:{target} "web.config" ext:config',
        'site:{target} ".htaccess" filetype:htaccess',
        'site:{target} ext:ini "database"',
        'site:{target} ext:cfg',
        'site:{target} "config.php" ext:php',
        'site:{target} ".gitignore" OR ".env" ext:env',
        'site:{target} "settings.py" inurl:settings',
    ],

    "database_dumps": [
        'site:{target} ext:sql "CREATE TABLE"',
        'site:{target} ext:sql "INSERT INTO"',
        'site:{target} ext:mdb',
        'site:{target} ext:sqlite',
        'site:{target} "db_dump" OR "database_dump"',
        'site:{target} filetype:sql "-- phpMyAdmin"',
    ],

    "log_files": [
        'site:{target} ext:log',
        'site:{target} "error_log" OR "access_log"',
        'site:{target} inurl:logs ext:txt',
        'site:{target} "exception" ext:log',
        'site:{target} intitle:"log file" ext:log',
        'site:{target} "debug" ext:log inurl:log',
    ],

    "api_keys": [
        'site:{target} "api_key" ext:json',
        'site:{target} "api_secret" ext:json',
        'site:{target} "stripe_key" OR "stripe_secret"',
        'site:{target} "aws_access_key_id"',
        'site:{target} "GOOGLE_API_KEY"',
        'site:{target} "Authorization: Bearer"',
        'site:{target} "token" ext:json inurl:api',
    ],

    "backup_files": [
        'site:{target} ext:zip',
        'site:{target} ext:tar',
        'site:{target} ext:7z',
        'site:{target} ext:rar',
        'site:{target} "backup" ext:zip',
        'site:{target} inurl:backup ext:tar.gz',
        'site:{target} "old" OR "backup" ext:sql',
    ],
}


# ─────────────────────────────────────────
# Dork Generator Class
# ─────────────────────────────────────────
class DorkGenerator:
    """
    Generates search dorks for a target domain.
    
    Usage:
        gen = DorkGenerator(target="example.com")
        dorks = gen.generate(categories=["file_exposure", "admin_panels"])
        # Returns list of {"category": ..., "query": ...}
    
    Phase 5: AI model will augment this with context-aware dork generation.
    """

    def __init__(self, target: str):
        self.target = target.strip().lower()

    def generate(
        self,
        categories: List[str] = None,
    ) -> List[Dict[str, str]]:
        """
        Generate dorks for the given categories.
        If categories is None, generate for ALL categories.
        
        Returns a list of dicts:
            [{"category": "file_exposure", "query": "site:example.com ext:sql"}, ...]
        """
        if categories is None:
            categories = list(DORK_TEMPLATES.keys())

        result = []

        for category in categories:
            templates = DORK_TEMPLATES.get(category, [])
            for template in templates:
                query = template.replace("{target}", self.target)
                result.append({
                    "category": category,
                    "query": query,
                })

        return result

    def generate_for_category(self, category: str) -> List[str]:
        """Return just the query strings for a single category."""
        templates = DORK_TEMPLATES.get(category, [])
        return [t.replace("{target}", self.target) for t in templates]

    @staticmethod
    def available_categories() -> List[str]:
        """Return all available dork categories."""
        return list(DORK_TEMPLATES.keys())

    @staticmethod
    def category_count() -> Dict[str, int]:
        """Return dork count per category."""
        return {cat: len(dorks) for cat, dorks in DORK_TEMPLATES.items()}

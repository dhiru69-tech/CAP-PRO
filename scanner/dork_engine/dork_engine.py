"""
ReconMind — scanner/dork_engine/dork_engine.py

Scanner-side dork engine. Generates dork queries based on target + depth.
Depth controls how many dorks are run per category:
  surface  → 3 dorks per category  (fast, broad)
  standard → 6 dorks per category  (balanced)
  deep     → all dorks per category (thorough)

Phase 6: AI model will replace static templates with dynamic,
context-aware dork generation based on target analysis.
"""

from typing import List, Dict

from scanner.utils.logger import get_logger
from scanner.utils.models import DorkResult

logger = get_logger("dork_engine")

# ─────────────────────────────────────────
# Dork template library
# {target} → replaced with actual domain
# ─────────────────────────────────────────
DORK_LIBRARY: Dict[str, List[str]] = {

    "file_exposure": [
        'site:{target} ext:sql',
        'site:{target} ext:bak',
        'site:{target} ext:log',
        'site:{target} ext:env',
        'site:{target} ext:dump',
        'site:{target} "index of" "backup"',
        'site:{target} "index of" "uploads"',
        'site:{target} intitle:"index of" "*.gz"',
        'site:{target} ext:old',
        'site:{target} ext:save',
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
        'site:{target} inurl:manage',
        'site:{target} intitle:"control panel"',
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
        'site:{target} "credentials" ext:xml',
        'site:{target} "passwd" ext:txt',
    ],

    "config_files": [
        'site:{target} ext:xml inurl:config',
        'site:{target} "web.config" ext:config',
        'site:{target} ".htaccess" filetype:htaccess',
        'site:{target} ext:ini "database"',
        'site:{target} ext:cfg',
        'site:{target} "config.php" ext:php',
        'site:{target} ".env" ext:env',
        'site:{target} "settings.py" inurl:settings',
        'site:{target} "application.properties"',
        'site:{target} ext:yaml inurl:config',
    ],

    "database_dumps": [
        'site:{target} ext:sql "CREATE TABLE"',
        'site:{target} ext:sql "INSERT INTO"',
        'site:{target} ext:mdb',
        'site:{target} ext:sqlite',
        'site:{target} "db_dump" OR "database_dump"',
        'site:{target} filetype:sql "-- phpMyAdmin"',
        'site:{target} ext:sql.gz',
        'site:{target} inurl:dump ext:sql',
    ],

    "log_files": [
        'site:{target} ext:log',
        'site:{target} "error_log" OR "access_log"',
        'site:{target} inurl:logs ext:txt',
        'site:{target} "exception" ext:log',
        'site:{target} intitle:"log file" ext:log',
        'site:{target} "debug" ext:log inurl:log',
        'site:{target} "Traceback" ext:log',
        'site:{target} inurl:error.log',
    ],

    "api_keys": [
        'site:{target} "api_key" ext:json',
        'site:{target} "api_secret" ext:json',
        'site:{target} "stripe_key" OR "stripe_secret"',
        'site:{target} "aws_access_key_id"',
        'site:{target} "GOOGLE_API_KEY"',
        'site:{target} "Authorization: Bearer"',
        'site:{target} "token" ext:json inurl:api',
        'site:{target} "service_account" ext:json',
    ],

    "backup_files": [
        'site:{target} ext:zip',
        'site:{target} ext:tar',
        'site:{target} ext:7z',
        'site:{target} ext:rar',
        'site:{target} "backup" ext:zip',
        'site:{target} inurl:backup ext:tar.gz',
        'site:{target} "old" OR "backup" ext:sql',
        'site:{target} ext:tgz',
    ],
}

# How many dorks per category based on depth
DEPTH_LIMITS = {
    "surface":  3,
    "standard": 6,
    "deep":     999,   # All
}


class DorkEngine:
    """
    Generates dork queries for the scanner pipeline.

    Usage:
        engine = DorkEngine()
        dorks = engine.generate(
            target="example.com",
            categories=["file_exposure", "admin_panels"],
            depth="standard"
        )
        # Returns list of DorkResult objects ready for Discovery
    """

    def generate(
        self,
        target: str,
        categories: List[str] = None,
        depth: str = "standard",
    ) -> List[dict]:
        """
        Generate dork query dicts for the given target.
        Returns list of {"category": ..., "query": ..., "dork_id": None}
        """
        target = target.strip().lower()
        limit = DEPTH_LIMITS.get(depth, 6)

        if categories is None:
            categories = list(DORK_LIBRARY.keys())

        results = []
        total = 0

        for category in categories:
            templates = DORK_LIBRARY.get(category, [])
            selected = templates[:limit]

            for template in selected:
                query = template.replace("{target}", target)
                results.append({
                    "category": category,
                    "query": query,
                    "dork_id": None,
                })
                total += 1

        logger.info(
            f"Generated {total} dorks for '{target}' | "
            f"depth={depth} | categories={len(categories)}"
        )
        return results

    @staticmethod
    def available_categories() -> List[str]:
        return list(DORK_LIBRARY.keys())

    @staticmethod
    def preview(target: str, category: str, depth: str = "standard") -> List[str]:
        """Quick preview of dorks for a single category."""
        limit = DEPTH_LIMITS.get(depth, 6)
        templates = DORK_LIBRARY.get(category, [])
        return [t.replace("{target}", target) for t in templates[:limit]]

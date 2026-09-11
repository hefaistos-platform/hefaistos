# Migration 0007: Multi-Domain Technique Support

## Purpose
Allows importing Enterprise, ICS, and Mobile ATT&CK techniques that may share the same technique_id (e.g., T1401 exists in both Enterprise and Mobile).

## Changes
- **Removed**: Global `unique=True` on `MitreAttackTechnique.technique_id`
- **Added**: Unique constraint on `(technique_id, domain)` pair

## Roll-forward (Apply)
```bash
python manage.py migrate platform_data 0007
```

## Rollback (Revert)
```bash
# WARNING: Only safe if no duplicate technique_ids across domains exist
python manage.py migrate platform_data 0006
```

**Rollback risk**: If ICS/Mobile data was already imported with overlapping IDs, rollback will fail due to constraint violation. In that case, you'd need to delete cross-domain duplicates first:
```python
# In Django shell
from platform_data.models import MitreAttackTechnique, MitreDomain
# Keep only Enterprise, remove ICS/Mobile duplicates
MitreAttackTechnique.objects.filter(domain__in=[MitreDomain.ICS, MitreDomain.MOBILE]).delete()
# Then rollback
```

## Post-Migration Steps
1. Apply migration: `python manage.py migrate`
2. Import ATT&CK data: `python manage.py import_mitre_universal --mitre-version 19.1 --mode remote`
3. Verify counts:
   ```python
   from platform_data.models import MitreAttackTechnique, MitreDomain
   print(f"Enterprise: {MitreAttackTechnique.objects.filter(domain=MitreDomain.ENTERPRISE).count()}")
   print(f"ICS: {MitreAttackTechnique.objects.filter(domain=MitreDomain.ICS).count()}")
   print(f"Mobile: {MitreAttackTechnique.objects.filter(domain=MitreDomain.MOBILE).count()}")
   ```

## Expected Results
- **Enterprise**: ~700+ techniques (including subtechniques)
- **ICS**: ~80+ techniques
- **Mobile**: ~70+ techniques

## Database Impact
- Existing Enterprise-only data: **No impact** (same technique_id + domain remains unique)
- New ICS/Mobile data: **Can now coexist** with same IDs as Enterprise
- Query changes: Add `.filter(domain=...)` when domain-specific queries needed

## UI Considerations (Optional Follow-ups)
- Technique pickers: Consider domain filter if showing non-Enterprise
- Coverage map: Currently hardcoded to `"domain": "enterprise-attack"` in views.py line 164
- Schema queries: May need domain awareness if exposing ICS/Mobile in GraphQL

# AACapital root-level Python import hotfix

This zip is intentionally root-relative. Extract/copy its contents directly into `C:\aacapital-v2`.

It fixes the Windows script invocation issue by removing package-style `_scripts...` imports from direct Python scripts.

Run:

```powershell
cd C:\aacapital-v2
Expand-Archive "$env:USERPROFILE\Downloads\aacapital-hotfix-20260617-root-python-fix.zip" -DestinationPath . -Force
python _scripts/prod/kite_sync_and_predict.py --mode all
python _scripts/ml/train_multibagger_model.py
npm run build
```

If local DB auth fails, verify this exact command works:

```powershell
psql "postgresql://postgres:Ashrith%402820@localhost:5432/aacapital?sslmode=disable" -c "select current_database(), current_user;"
```

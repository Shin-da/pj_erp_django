# Recreate catalogs if missing, migrate, import the FTP MSSQL snapshot into prod, copy into dev.
# Run from pj-erp:  powershell -File scripts\setup_databases.ps1
#
# pj_dev cannot CREATE DATABASE. Catalogs are created (once) as the Postgres
# superuser, then owned by pj_dev. Set PG_SUPERUSER_PASSWORD if postgres isn't passwordless.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $Root "manage.py"))) { $Root = Get-Location }
Set-Location $Root

function Assert-Exit($step) {
    if ($LASTEXITCODE -ne 0) { throw "$step failed (exit $LASTEXITCODE)" }
}

$Py = Join-Path $Root "venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { $Py = "python" }

$Psql = $null
$cmd = Get-Command psql -ErrorAction SilentlyContinue
if ($cmd) { $Psql = $cmd.Source }
if (-not $Psql) {
    foreach ($c in @(
        "C:\Program Files\PostgreSQL\16\bin\psql.exe",
        "C:\Program Files\PostgreSQL\15\bin\psql.exe",
        "C:\Program Files\PostgreSQL\14\bin\psql.exe"
    )) {
        if (Test-Path $c) { $Psql = $c; break }
    }
}
if (-not $Psql) { throw "psql not found. Add PostgreSQL bin to PATH." }

function Invoke-Psql($user, $password, $database, $sql) {
    $saved = $env:PGPASSWORD
    $env:PGPASSWORD = $password
    $out = & $Psql -U $user -h localhost -d $database -v ON_ERROR_STOP=1 -tAc $sql 2>&1
    $code = $LASTEXITCODE
    $env:PGPASSWORD = $saved
    return @{ Code = $code; Out = ($out | Out-String).Trim() }
}

function Find-Superuser {
    $passwords = @()
    if ($env:PG_SUPERUSER_PASSWORD) { $passwords += $env:PG_SUPERUSER_PASSWORD }
    $passwords += @("postgres", "pj_dev_local", "")
    foreach ($pw in $passwords) {
        $r = Invoke-Psql "postgres" $pw "postgres" "SELECT current_user"
        if ($r.Code -eq 0 -and $r.Out -match "postgres") {
            return $pw
        }
    }
    return $null
}

function Catalog-Exists($name) {
    $r = Invoke-Psql "pj_dev" "pj_dev_local" "postgres" "SELECT 1 FROM pg_database WHERE datname = '$name'"
    return ($r.Code -eq 0 -and $r.Out -eq "1")
}

$devOk = Catalog-Exists "pj_erp_dev"
$prodOk = Catalog-Exists "pj_erp_prod"

if (-not ($devOk -and $prodOk)) {
    Write-Host "Connecting as Postgres superuser to create missing catalogs..."
    $superPw = Find-Superuser
    if ($null -eq $superPw) {
        Write-Host "Could not log in as Postgres superuser (user postgres)."
        Write-Host "Run: psql -U postgres -h localhost -d postgres"
        Write-Host "Then: ALTER USER pj_dev WITH CREATEDB;"
        Write-Host "      CREATE DATABASE pj_erp_dev OWNER pj_dev;"
        Write-Host "      CREATE DATABASE pj_erp_prod OWNER pj_dev;"
        Write-Host "Or set PG_SUPERUSER_PASSWORD and re-run this script."
        exit 1
    }

    Write-Host "Granting CREATEDB to pj_dev and ensuring both catalogs exist..."
    $grant = Invoke-Psql "postgres" $superPw "postgres" "ALTER USER pj_dev WITH CREATEDB"
    if ($grant.Code -ne 0) { throw "ALTER USER pj_dev CREATEDB failed: $($grant.Out)" }

    foreach ($db in @("pj_erp_dev", "pj_erp_prod")) {
        $exists = Invoke-Psql "postgres" $superPw "postgres" "SELECT 1 FROM pg_database WHERE datname = '$db'"
        if ($exists.Out -ne "1") {
            Write-Host "  creating $db..."
            $create = Invoke-Psql "postgres" $superPw "postgres" "CREATE DATABASE $db OWNER pj_dev"
            if ($create.Code -ne 0) { throw "CREATE DATABASE $db failed: $($create.Out)" }
        } else {
            Write-Host "  $db already exists"
        }
    }
} else {
    Write-Host "Both catalogs already exist - skipping superuser."
}

Write-Host "Migrating + importing PROD snapshot..."
$env:DJANGO_DB_PROFILE = "prod"
$env:PGPASSWORD = "pj_dev_local"
& $Py manage.py migrate
Assert-Exit "migrate prod"
& $Py manage.py import_mssql_snapshot --flush
Assert-Exit "import prod"

Write-Host "Copying prod snapshot into the dev working copy (schema wipe, no DROP DATABASE)..."
& $Py manage.py clone_prod_to_dev --yes
Assert-Exit "clone prod -> dev"

$env:DJANGO_DB_PROFILE = "dev"
& $Py manage.py migrate
Assert-Exit "migrate dev"
& $Py manage.py ensure_local_admin
Assert-Exit "ensure local admin on dev"

Write-Host "Done. Leave DJANGO_DB_PROFILE=dev in .env for day-to-day work."
Write-Host "Local login: employee code 1001 / password changeme123"
Write-Host "Flip to prod in .env and restart runserver to browse the frozen snapshot."

@echo off
REM ============================================================
REM  EcomKbAgent frontend dependency installer (pnpm, Windows)
REM  Purpose: install frontend deps safely even though a system
REM           proxy blocks pnpm by default.
REM  How: clear the 4 proxy vars for THIS pnpm process only,
REM       then install from the China mirror with retries.
REM  Usage: double-click this file, or run it from PyCharm as
REM         a "Shell Script" run configuration.
REM ============================================================
setlocal

REM Clear proxy vars for this process only (the key step)
set HTTP_PROXY=
set HTTPS_PROXY=
set http_proxy=
set https_proxy=

REM Move into the folder that holds this .bat (frontend/)
cd /d "%~dp0"

echo [install-deps-pnpm] Proxy cleared. Installing from China mirror...
pnpm install --registry=https://registry.npmmirror.com --fetch-retries=5 --fetch-retry-mintimeout=20000 --fetch-retry-maxtimeout=120000
if %errorlevel%==0 (echo [install-deps-pnpm] Install succeeded.) else (echo [install-deps-pnpm] Install failed.)

endlocal
pause

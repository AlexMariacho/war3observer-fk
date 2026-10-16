@echo off
setlocal EnableExtensions
rem Sets up, builds and runs war3observer in one go. Steps that are already
rem done (dependencies installed, icons extracted for this game build) are
rem skipped on the next run.
rem
rem Usage: run.bat [fake] [rebuild] [noopen] [view NAME]
rem   fake       also start tools\fake_observer_api.py (no Warcraft III needed)
rem   rebuild    reinstall dependencies and re-extract icons
rem   noopen     don't open the control panel in the browser
rem   view NAME  overlay page to suggest for OBS (default: de-1v1-overview)
rem
rem Set WC3_DIR to override the Warcraft III installation directory.

cd /d "%~dp0"

if not defined WC3_DIR set "WC3_DIR=S:\Programs\Battlenet\Games\Warcraft III"
set "VIEW=de-1v1-overview"
set "FAKE="
set "REBUILD="
set "NOOPEN="
set "TOTAL=6"

:parse
if "%~1"=="" goto parsed
if /i "%~1"=="fake" (set "FAKE=1" & shift & goto parse)
if /i "%~1"=="rebuild" (set "REBUILD=1" & shift & goto parse)
if /i "%~1"=="noopen" (set "NOOPEN=1" & shift & goto parse)
if /i "%~1"=="view" (set "VIEW=%~2" & shift & shift & goto parse)
echo Unknown argument: %~1
echo Usage: run.bat [fake] [rebuild] [noopen] [view NAME]
exit /b 1
:parsed

set "PY=%CD%\.venv\Scripts\python.exe"
set "WC3_RUNNING="
tasklist /fi "imagename eq Warcraft III.exe" 2>nul | "%SystemRoot%\System32\find.exe" /i "Warcraft III.exe" >nul && set "WC3_RUNNING=1"

rem ---------------------------------------------------------------------------
call :step 1 "Checking tools"

where python >nul 2>&1 || (call :fail "Python is not in PATH. Install Python 3.12+ from python.org" & exit /b 1)
for /f "delims=" %%v in ('python --version 2^>^&1') do echo       %%v
where npm >nul 2>&1 || (call :fail "npm is not in PATH. Install Node.js from nodejs.org" & exit /b 1)
for /f "delims=" %%v in ('node --version') do echo       Node.js %%v
call :ok "Python and Node.js found"

rem ---------------------------------------------------------------------------
call :step 2 "Python environment (.venv)"

if exist "%PY%" goto venv_ready
echo       Creating .venv...
python -m venv .venv || (call :fail "Could not create .venv" & exit /b 1)
:venv_ready

copy /y /b requirements.txt+requirements-dev.txt "%TEMP%\w3o-requirements.txt" >nul
set "NEED="
if defined REBUILD set "NEED=1"
if not exist ".venv\requirements.stamp" set "NEED=1"
if not defined NEED fc /b "%TEMP%\w3o-requirements.txt" ".venv\requirements.stamp" >nul 2>&1 || set "NEED=1"

if not defined NEED (
  echo       Dependencies are up to date
  goto venv_check
)
where git >nul 2>&1 || (call :fail "git is not in PATH, it is needed to install war3structs" & exit /b 1)
echo       Installing Python dependencies, this can take a minute...
"%PY%" -m pip install -q --disable-pip-version-check -r requirements.txt -r requirements-dev.txt || (call :fail "pip install failed, see the output above" & exit /b 1)
copy /y "%TEMP%\w3o-requirements.txt" ".venv\requirements.stamp" >nul

:venv_check
"%PY%" -c "import war3observer, war3structs.observer, websockets, PIL" || (call :fail "Python dependencies are broken, rerun with: run.bat rebuild" & exit /b 1)
call :ok "Python environment ready"

rem ---------------------------------------------------------------------------
call :step 3 "Building the client (client\dist)"

pushd client
set "NEED="
if defined REBUILD set "NEED=1"
if not exist "node_modules\package.stamp" set "NEED=1"
if not defined NEED fc /b package.json "node_modules\package.stamp" >nul 2>&1 || set "NEED=1"

if not defined NEED (
  echo       Node.js dependencies are up to date
  goto client_build
)
echo       Installing Node.js dependencies...
call npm install --no-fund --no-audit --loglevel=error || (popd & call :fail "npm install failed, see the output above" & exit /b 1)
copy /y package.json "node_modules\package.stamp" >nul

:client_build
echo       Running webpack...
call npm run build --silent -- --stats=errors-warnings || (popd & call :fail "Client build failed, see the output above" & exit /b 1)
popd

set "VIEWS=0"
for %%f in (client\dist\*.html) do set /a VIEWS+=1
if not exist "client\dist\%VIEW%.html" (call :fail "View %VIEW% was not built. Available views are the .html files in client\dist" & exit /b 1)
call :ok "Client built, %VIEWS% views in client\dist"

rem ---------------------------------------------------------------------------
call :step 4 "Extracting icons from Warcraft III"

set "STAMP=client\dist\icons\.game-version"
set "OLDVER="
if exist "%STAMP%" set /p OLDVER=<"%STAMP%"

if exist "%WC3_DIR%\.build.info" goto icons_game_found
if defined OLDVER (
  call :warn "Warcraft III not found at %WC3_DIR%, keeping icons from build %OLDVER%"
) else (
  call :warn "Warcraft III not found at %WC3_DIR%, overlay icons will show placeholders. Set WC3_DIR and rerun"
)
goto icons_done

:icons_game_found
"%PY%" -c "import re,sys; m=re.findall(r'\d+\.\d+\.\d+\.\d+', open(sys.argv[1], encoding='utf-8', errors='replace').read()); print(m[-1] if m else 'unknown')" "%WC3_DIR%\.build.info" > "%TEMP%\w3o-gamever.txt"
set "GAMEVER=unknown"
set /p GAMEVER=<"%TEMP%\w3o-gamever.txt"
echo       Game build: %GAMEVER%

if defined REBUILD goto icons_extract
if not "%OLDVER%"=="%GAMEVER%" goto icons_extract
call :ok "Icons are up to date for build %GAMEVER%"
goto icons_done

:icons_extract
rem A running game locks its files, so extraction would fail
if defined WC3_RUNNING goto icons_locked
if defined OLDVER echo       Icons were extracted from build %OLDVER%, re-extracting...
"%PY%" tools\extract_icons.py "%WC3_DIR%" client\dist\icons && goto icons_written
call :warn "Icon extraction failed, see the output above. The overlay still works, missing icons show a placeholder"
goto icons_done

:icons_written
> "%STAMP%" echo %GAMEVER%
call :ok "Icons extracted to client\dist\icons (sd, hd, de)"
goto icons_done

:icons_locked
if defined OLDVER (
  call :warn "Warcraft III is running and locks its files. Keeping icons from build %OLDVER%, close the game and rerun to update them"
) else (
  call :warn "Warcraft III is running and locks its files. Close the game and rerun once to extract icons, until then icons show a placeholder"
)

:icons_done

rem ---------------------------------------------------------------------------
call :step 5 "Observer API source"

if not defined FAKE goto no_fake
echo       Starting tools\fake_observer_api.py in a separate window...
start "war3observer fake API" "%PY%" tools\fake_observer_api.py
ping -n 3 127.0.0.1 >nul
call :ok "Fake observer API running, close its window to stop it"
goto api_done

:no_fake
if defined WC3_RUNNING (
  call :ok "Warcraft III is running. Open a replay or observe a game"
) else (
  call :warn "Warcraft III is not running yet. Start it and open a replay or observe a game, the server will pick it up"
)

:api_done

rem ---------------------------------------------------------------------------
call :step 6 "Starting the server"

rem A server left over from a previous run would keep the port and run old code
set "OLDPID="
set "OLDNAME="
for /f "tokens=5" %%p in ('netstat -ano ^| "%SystemRoot%\System32\findstr.exe" /r /c:":8124 .*LISTENING"') do set "OLDPID=%%p"
if not defined OLDPID goto server_open
for /f "tokens=1" %%n in ('tasklist /fi "pid eq %OLDPID%" /nh') do set "OLDNAME=%%n"
if /i not "%OLDNAME%"=="python.exe" (call :fail "Port 8124 is used by another program: %OLDNAME% PID %OLDPID%" & exit /b 1)
echo       Stopping the previous war3observer server, PID %OLDPID%...
taskkill /pid %OLDPID% /f >nul 2>&1
ping -n 2 127.0.0.1 >nul

:server_open
if defined NOOPEN goto server_start
echo       Opening the control panel in the browser...
start "" "%CD%\client\dist\control-panel.html"

:server_start
echo       Overlay for OBS:  Browser Source, Local file = %CD%\client\dist\%VIEW%.html, 1920x1080
echo       Control panel:    file:///%CD:\=/%/client/dist/control-panel.html
echo                         (OBS: View, Docks, Custom Browser Docks, to keep it inside OBS)
echo       Server log follows. Press Ctrl+C to stop.
echo.
"%PY%" -m war3observer
if errorlevel 1 (call :fail "The server stopped with an error, see the log above. Is port 8124 already in use?" & exit /b 1)
echo.
echo Server stopped.
exit /b 0

rem ---------------------------------------------------------------------------
:step
echo.
echo [%~1/%TOTAL%] %~2...
exit /b 0

:ok
echo       OK: %~1
exit /b 0

:warn
echo       WARNING: %~1
exit /b 0

:fail
echo.
echo       FAILED: %~1
echo.
pause
exit /b 1

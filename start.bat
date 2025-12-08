@echo off
setlocal

set "VENV_NAME=.venv"
set "PYTHON_VERSION=3.12" :: Telegram bot 库 20.7 版本不支持 3.14
set "PYTHON_SCRIPT=watchdog.py" :: 引入 watchdog 管理 main.py 的生命周期
set "REQUIREMENTS_FILE=requirements.txt"

echo ######################################################
echo # Telegram Bot Launcher (Python %PYTHON_VERSION%)
echo ######################################################

:: 1. 若无虚拟环境则创建
echo [1/3] Checking/Creating virtual environment...
if not exist "%VENV_NAME%\Scripts\activate.bat" (
    echo Creating venv using py -%PYTHON_VERSION%...
    :: 使用 py -3.12 确保使用正确的 Python 版本创建 venv
    py -%PYTHON_VERSION% -m venv "%VENV_NAME%"
    
    :: 检查创建是否失败
    if errorlevel 1 (
        echo ERROR: Failed to create venv. Is Python %PYTHON_VERSION% installed?
        goto :end
    )
) else (
    echo Virtual environment already exists. [cite: 2]
)

:: 2. 激活虚拟环境
echo [2/3] Activating virtual environment...
call "%VENV_NAME%\Scripts\activate.bat"

:: 3. 安装依赖 (仅在存在 requirements.txt 时) 并启动脚本
echo [3/3] Installing dependencies and launching bot...
if exist "%REQUIREMENTS_FILE%" (
    pip install -r "%REQUIREMENTS_FILE%"
    :: 检查安装是否失败
    if errorlevel 1 (
        echo ERROR: Failed to install packages.
        echo Check your internet connection. [cite: 3]
        goto :deactivate
    )
) else (
    echo WARNING: %REQUIREMENTS_FILE% not found. Skipping dependency installation.
)

:: 启动看门狗脚本，由它来循环启动 main.py
echo Launching %PYTHON_SCRIPT% (Watchdog)...
python "%PYTHON_SCRIPT%"

:deactivate
echo Deactivating virtual environment...
call deactivate

:end
echo. [cite: 4]
pause
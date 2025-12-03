@echo off
setlocal

set "VENV_NAME=venv"
set "PYTHON_VERSION=3.12"
set "PYTHON_SCRIPT=main.py"
set "REQUIREMENTS_FILE=requirements.txt"

echo ######################################################
echo # 机器人启动脚本 (Python %PYTHON_VERSION%)
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
    echo Virtual environment already exists.
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
        echo ERROR: Failed to install packages. Check your internet connection.
        goto :deactivate
    )
) else (
    echo WARNING: %REQUIREMENTS_FILE% not found. Skipping dependency installation.
)

echo Launching %PYTHON_SCRIPT%...
python "%PYTHON_SCRIPT%"

:deactivate
echo Deactivating virtual environment...
call deactivate

:end
echo.
pause
@echo off
setlocal

set "VENV_NAME=.venv"
set "PYTHON_VERSION=3.12" :: 建议使用稳定版本
set "PYTHON_SCRIPT=watchdog.py" :: 启动看门狗管理主程序

set "REQUIREMENTS_FILE=requirements.txt"

echo ######################################################
echo # Telegram Bot 启动器 (Python %PYTHON_VERSION%)
echo ######################################################

:: 1. 若无虚拟环境则创建
echo [1/4] 检查/创建虚拟环境...
if not exist "%VENV_NAME%\Scripts\activate.bat" (
    echo 正在使用 py -%PYTHON_VERSION% 创建虚拟环境...
    :: 使用 py -3.12 确保使用正确的 Python 版本创建 venv
    py -%PYTHON_VERSION% -m venv "%VENV_NAME%"
    
    :: 检查创建是否失败
    if errorlevel 1 (
        echo ERROR: 创建虚拟环境失败。请确认是否安装了 Python %PYTHON_VERSION% 并已添加到 PATH。
        goto :end
    )
) else (
    echo 虚拟环境已存在，跳过创建。
)

:: 2. 激活虚拟环境
echo [2/4] 激活虚拟环境...
call "%VENV_NAME%\Scripts\activate.bat"

:: 3. 安装依赖并启动脚本
echo [3/4] 安装依赖并启动机器人看门狗...
if exist "%REQUIREMENTS_FILE%" (
    pip install -r "%REQUIREMENTS_FILE%"
    :: 检查安装是否失败
    if errorlevel 1 (
        echo ERROR: 安装依赖包失败。请检查网络连接或 requirements.txt 文件。
        goto :deactivate
    )
) else (
    echo WARNING: %REQUIREMENTS_FILE% 文件未找到。跳过依赖安装。
)

:: 4. 检查 config.json 文件是否存在
echo [4/4] 检查配置文件...
set "CONFIG_FILE=config.json"
set "CONFIG_TEMPLATE=config.json.example"

if not exist "%CONFIG_FILE%" (
    if exist "%CONFIG_TEMPLATE%" (
        echo WARNING: 配置文件 %CONFIG_FILE% 不存在，正在从模板 %CONFIG_TEMPLATE% 复制一份。
        copy "%CONFIG_TEMPLATE%" "%CONFIG_FILE%"
        echo 请编辑 %CONFIG_FILE% 以配置您的机器人。
    ) else (
        echo ERROR: 配置文件 %CONFIG_FILE% 和模板 %CONFIG_TEMPLATE% 均不存在！无法启动。
        goto :deactivate
    )
) else (
    echo 配置文件 %CONFIG_FILE% 已存在，跳过创建。
)

:: 5. 启动看门狗脚本，由它来循环启动 main.py
echo 启动 %PYTHON_SCRIPT% (看门狗)...
python "%PYTHON_SCRIPT%"

:deactivate
echo 停用虚拟环境...
call deactivate

:end
echo.
pause
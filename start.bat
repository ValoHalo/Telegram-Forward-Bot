@echo off
chcp 65001 > nul
>nul set /p "=." <nul

setlocal
@echo off
set "VENV_NAME=.venv"
set "PYTHON_VERSION=3.13" 
set "PYTHON_SCRIPT=watchdog.py"
set "REQUIREMENTS_FILE=requirements.txt"
set "CONFIG_FILE=config.json"
set "CONFIG_TEMPLATE=config.json.example"

echo ######################################################
echo # Telegram Bot 启动器 (Python %PYTHON_VERSION%)
echo ######################################################

echo [1/5] 检查/创建虚拟环境...
if not exist "%VENV_NAME%\Scripts\activate.bat" (
    echo 正在使用 py -%PYTHON_VERSION% 创建虚拟环境...
    py -%PYTHON_VERSION% -m venv "%VENV_NAME%"
    if errorlevel 1 (
        echo ❌ 错误: 创建虚拟环境失败。请确认是否安装了 Python %PYTHON_VERSION%。
        goto :end
    )
) else (
    echo ✅ 虚拟环境已存在，跳过创建。
)

echo [2/5] 激活虚拟环境...
call "%VENV_NAME%\Scripts\activate.bat"
if errorlevel 1 (
  echo ❌ 错误: 激活虚拟环境失败。
    goto :end
)
echo ✅ 虚拟环境激活成功。

echo [3/5] 检查配置文件 (%CONFIG_FILE%) ...
if not exist "%CONFIG_FILE%" (
    if exist "%CONFIG_TEMPLATE%" (
        echo ⚠️ 配置文件 %CONFIG_FILE% 不存在，正在从模板 %CONFIG_TEMPLATE% 复制。
        copy "%CONFIG_TEMPLATE%" "%CONFIG_FILE%" >nul
        echo ➡️ 请编辑 %CONFIG_FILE% 配置您的 Token 和 Owner ID。
    ) else (
        echo ❌ 错误: 模板文件 %CONFIG_TEMPLATE% 也不存在。请先运行 git pull 更新代码。
        goto :deactivate
    )
) else (
    echo ✅ 配置文件 %CONFIG_FILE% 已存在。
)


echo [4/5] 安装依赖 (在虚拟环境中执行)...
if exist "%REQUIREMENTS_FILE%" (
    echo 正在更新 pip 工具...
    python.exe -m pip install --upgrade pip -q
    
    pip install -r "%REQUIREMENTS_FILE%" -q
    if errorlevel 1 (
        echo ❌ 错误: 安装依赖包失败。请检查网络连接。
        goto :deactivate
    )
    echo ✅ 依赖安装/检查完成。
) else (
    echo ⚠️ %REQUIREMENTS_FILE% 文件未找到。跳过依赖安装。
)


echo [5/5] 启动 %PYTHON_SCRIPT% (看门狗)...
python "%PYTHON_SCRIPT%"

:deactivate
echo 停用虚拟环境...
call deactivate

:end
echo.
pause
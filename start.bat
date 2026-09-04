@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo   舆情对抗测试工具 - 一键启动
echo ============================================
echo.

rem ---------- 检测 Python ----------
where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未检测到 Python，请先安装 Python 3.9+ 并勾选 "Add python.exe to PATH"
    echo.
    pause
    exit /b 1
)

rem ---------- 若 18080 端口已有服务在跑，直接打开页面 ----------
netstat -ano | findstr "LISTENING" | findstr ":18080" >nul 2>nul
if not errorlevel 1 (
    echo [提示] 检测到服务已在 18080 端口运行，直接打开页面。
    start "" http://127.0.0.1:18080
    echo.
    pause
    exit /b 0
)

rem ---------- 检查依赖，缺失则安装 ----------
echo [1/3] 检查依赖...
python -c "import lxml, openpyxl" >nul 2>nul
if errorlevel 1 (
    echo   - 检测到缺少依赖，正在安装（lxml、openpyxl）...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo [错误] 依赖安装失败，请检查网络后手动执行：pip install -r requirements.txt
        echo.
        pause
        exit /b 1
    )
    echo   - 依赖安装完成
) else (
    echo   - 依赖已就绪
)

rem ---------- 启动服务 ----------
echo [2/3] 启动服务...
start "舆情对抗测试工具" python main.py

rem ---------- 等待服务就绪并打开浏览器 ----------
echo [3/3] 等待服务启动并打开页面...
set PORT=18080
for /l %%i in (1,1,30) do (
    timeout /t 1 /nobreak >nul
    netstat -ano | findstr "LISTENING" | findstr ":18080" >nul 2>nul
    if not errorlevel 1 goto :opened
)
echo [提示] 服务启动较慢，请稍后手动访问 http://127.0.0.1:%PORT%
goto :done

:opened
start "" http://127.0.0.1:%PORT%
echo   服务已启动：http://127.0.0.1:%PORT%

:done
echo.
echo 说明：关闭本窗口不会停止服务；如需停止，请关闭标题为
echo      「舆情对抗测试工具」的窗口，或结束对应 python 进程。
echo.
pause

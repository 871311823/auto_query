@echo off
chcp 65001 >nul
title auto_query firewall rule

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo 需要管理员权限，正在请求提权...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

echo 正在删除旧规则（如存在）...
netsh advfirewall firewall delete rule name="auto_query_web" >nul 2>&1

echo 正在添加防火墙入站规则：端口 18080-18099，专用 + 公用网络...
netsh advfirewall firewall add rule name="auto_query_web" dir=in action=allow protocol=TCP localport=18080-18099 profile=private,public

echo.
echo 完成。防火墙规则已添加。
echo 现在启动 python main.py 就不会再弹出网络访问提示了。
echo.
pause

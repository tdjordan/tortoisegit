::
:: Win32 batch file to handle TortoiseGit external proc calls
::

@echo off
setlocal

:: Look in the registry for TortoiseGit location
for /f "skip=2 tokens=3*" %%A in (
    '"reg query "HKEY_LOCAL_MACHINE\SOFTWARE\TortoiseGit" /ve 2> nul"' ) do set TortoisePath=%%B
if "%TortoisePath%"=="" (goto :notfound) else (goto :gitproc)

:gitproc
python "%TortoisePath%\gitproc.py" %*
goto end

:notfound
echo gitproc: cannot find TortoiseGit location in the registry.

:end

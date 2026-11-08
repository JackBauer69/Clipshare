Unicode true
RequestExecutionLevel user

!include "MUI2.nsh"
!ifndef APP_VERSION
  !define APP_VERSION "0.1.0"
!endif
!ifndef PROJECT_ROOT
  !define PROJECT_ROOT "../.."
!endif
!include "${PROJECT_ROOT}\\build\\spec\\clipshare_uninstall.nsh"

Name "ClipShare ${APP_VERSION}"
!ifndef OUTPUT_FILE
  !define OUTPUT_FILE "${PROJECT_ROOT}\\build\\artifacts\\ClipShare-${APP_VERSION}-windows-x64-setup.exe"
!endif
OutFile "${OUTPUT_FILE}"
InstallDir "$LOCALAPPDATA\Programs\ClipShare"

!define MUI_ABORTWARNING
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Section "ClipShare application" SEC_APP
  SetShellVarContext current
  SectionIn RO
  SetOutPath "$INSTDIR"
  File /r "${PROJECT_ROOT}\\build\\frozen\\ClipShare\\*"
  CreateDirectory "$SMPROGRAMS\ClipShare"
  CreateShortcut "$SMPROGRAMS\ClipShare\ClipShare.lnk" "$INSTDIR\ClipShare.exe"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ClipShare" "DisplayName" "ClipShare"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ClipShare" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ClipShare" "UninstallString" "$\"$INSTDIR\Uninstall.exe$\""
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ClipShare" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ClipShare" "NoRepair" 1
SectionEnd

Section "Uninstall"
  SetShellVarContext current
  Delete "$SMPROGRAMS\ClipShare\ClipShare.lnk"
  RMDir "$SMPROGRAMS\ClipShare"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ClipShare"
  Delete "$INSTDIR\Uninstall.exe"
  ; The generated manifest removes only application files and empty directories.
  Call un.RemoveBundleFiles
SectionEnd

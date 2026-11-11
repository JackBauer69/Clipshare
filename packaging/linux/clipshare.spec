Name:           clipshare
%global debug_package %{nil}
Version:        %{clipshare_version}
Release:        1%{?dist}
Summary:        Temporary local-network text and file sharing
License:        LicenseRef-ClipShare-Owner-Choice
Packager:       %{clipshare_maintainer}
Source0:        clipshare-bundle.tar.gz
Source1:        clipshare.desktop
BuildArch:      x86_64
Requires:       glibc >= 2.35

%description
ClipShare shares text, files, and folders between devices on a trusted local
network. Shared content is temporary and is removed when the app stops.

%prep
%setup -q -n clipshare

%build

%install
mkdir -p %{buildroot}/opt/clipshare
cp -a . %{buildroot}/opt/clipshare/
mkdir -p %{buildroot}%{_datadir}/applications
install -m 0644 %{SOURCE1} %{buildroot}%{_datadir}/applications/clipshare.desktop

%files
/opt/clipshare
%{_datadir}/applications/clipshare.desktop

%changelog
* Fri Nov 06 2026 ClipShare maintainers - 0.1.0-1
- Initial cross-platform package

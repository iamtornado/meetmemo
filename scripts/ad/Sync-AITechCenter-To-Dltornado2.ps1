param(
    [string] $SourceServer = "mywind.com.cn",
    [string] $TargetServer = "dltornado2.com",
    [string] $SourceDc = "",
    [string] $TargetDc = "",
    [string] $SourceDomainNetbios = "MYWIND",
    [string] $TargetDomainNetbios = "DLTORNADO2",
    [PSCredential] $SourceCredential,
    [PSCredential] $TargetCredential,
    [string] $SamAccountSuffix = "",
    [string] $DefaultPassword = "ChangeMe!2026",
    [switch] $SkipGroups,
    [switch] $WhatIf,
    [string] $SaveCsv = ""
)

# Sync AI Tech Center OU/users: mywind.com.cn -> dltornado2.com (under myse\IT)
# Requires RSAT ActiveDirectory module, Windows PowerShell 5.1+

$ErrorActionPreference = "Stop"

# --- DN paths ---
$SourceSearchBase = "OU=人工智能技术中心,OU=中央研究院,OU=明阳智慧能源集团股份公司,DC=mywind,DC=com,DC=cn"
$SourceDomainSuffix = "OU=明阳智慧能源集团股份公司,DC=mywind,DC=com,DC=cn"
$TargetDomainSuffix = "OU=IT,OU=myse,DC=dltornado2,DC=com"
$TargetRootOu = "OU=中央研究院," + $TargetDomainSuffix
$AiTechOuDn = "OU=人工智能技术中心," + $TargetRootOu

function Ensure-ADModule {
    if (-not (Get-Module -ListAvailable -Name ActiveDirectory)) {
        throw "ActiveDirectory module not found. Install RSAT."
    }
    Import-Module ActiveDirectory -ErrorAction Stop
}

function Get-ServerParams {
    param(
        [string] $Server,
        [PSCredential] $Credential,
        [ValidateSet("Negotiate", "Basic")]
        [string] $AuthType = "Negotiate"
    )
    $result = @{
        Server   = $Server
        AuthType = $AuthType
    }
    if ($null -ne $Credential) {
        $result.Credential = $Credential
    }
    return $result
}

function Normalize-DomainCredential {
    param(
        [PSCredential] $Credential,
        [string] $NetBiosDomain,
        [string] $UpnSuffix
    )
    if ($null -eq $Credential) { return $null }
    $user = $Credential.UserName
    if ($user -match "\\") { return $Credential }
    if ($user -match "@") { return $Credential }
    $withNetBios = ($NetBiosDomain + "\" + $user)
    Write-Host ("    Credential normalized to: " + $withNetBios + " (was: " + $user + ")") -ForegroundColor DarkGray
    return New-Object System.Management.Automation.PSCredential($withNetBios, $Credential.Password)
}

function Resolve-DomainController {
    param(
        [string] $DomainName,
        [string] $PreferredDc,
        [PSCredential] $Credential
    )
    if ($PreferredDc -ne "") {
        Write-Host ("    Using specified DC: " + $PreferredDc) -ForegroundColor DarkGray
        return $PreferredDc
    }
    try {
        $dc = Get-ADDomainController -Discover -DomainName $DomainName -Credential $Credential -ErrorAction Stop
        Write-Host ("    Discovered DC: " + $dc.HostName) -ForegroundColor DarkGray
        return $dc.HostName
    }
    catch {
        Write-Host ("    DC discovery failed, fallback to domain name: " + $DomainName) -ForegroundColor Yellow
        return $DomainName
    }
}

function Test-ADConnection {
    param(
        [string] $Label,
        [hashtable] $ServerParams,
        [string] $SearchBase
    )
    Write-Host (">>> Test connection: " + $Label) -ForegroundColor Cyan
    Write-Host ("    Server: " + $ServerParams.Server)
    try {
        $null = Get-ADObject @ServerParams -SearchBase $SearchBase -SearchScope Base -Filter * -Properties distinguishedName
        Write-Host "    OK" -ForegroundColor Green
    }
    catch {
        Write-Host ""
        Write-Host "AD connection failed. Common fixes:" -ForegroundColor Red
        Write-Host "  1) Use domain admin or account with read rights on the OU"
        Write-Host "  2) Credential format: MYWIND\youruser  OR  youruser@mywind.com.cn"
        Write-Host "  3) Specify a real DC hostname, e.g.:"
        Write-Host "     -SourceDc dc01.mywind.com.cn  -TargetDc dc01.dltornado2.com"
        Write-Host "  4) Ensure this PC can reach the DC (ping/nslookup, firewall port 389/636)"
        Write-Host "  5) If PC is joined to test domain only, production creds must be explicit (script already prompts)"
        Write-Host ""
        throw
    }
}

function ConvertTo-TargetDn {
    param([string] $SourceDn)
    if ($SourceDn -notlike ("*" + $SourceDomainSuffix)) {
        throw ("DN suffix mismatch: " + $SourceDn)
    }
    return $SourceDn.Replace($SourceDomainSuffix, $TargetDomainSuffix)
}

function Get-ParentDn {
    param([string] $Dn)
    $idx = $Dn.IndexOf(",")
    if ($idx -lt 0) {
        throw ("Invalid DN: " + $Dn)
    }
    return $Dn.Substring($idx + 1)
}

function Get-OuDepth {
    param([string] $Dn)
    return @($Dn -split ",").Count
}

function Read-SourceSubtree {
    param([hashtable] $SourceParams)

    Write-Host (">>> [1/2] Read from production: " + $SourceSearchBase) -ForegroundColor Cyan

    # NOTE: put @SourceParams first; never write "-Properties ..., Description, ... @Splat"
    # or PowerShell 5.1 may bind "Description" as a separate parameter and prompt for Filter.
    $ouProps = @("Name", "Description", "DistinguishedName")
    $ous = @(Get-ADOrganizationalUnit @SourceParams `
        -SearchBase $SourceSearchBase -SearchScope Subtree -Filter * -Properties $ouProps)

    $userProps = @(
        "SamAccountName", "UserPrincipalName", "DisplayName", "GivenName", "Surname",
        "EmailAddress", "Title", "Department", "Description", "Enabled", "DistinguishedName"
    )
    $users = @(Get-ADUser @SourceParams `
        -SearchBase $SourceSearchBase -SearchScope Subtree -Filter * -Properties $userProps)

    $groups = @()
    $memberRows = @()
    if (-not $SkipGroups) {
        $groupProps = @("Name", "Description", "GroupCategory", "GroupScope", "DistinguishedName", "Member")
        $groups = @(Get-ADGroup @SourceParams `
            -SearchBase $SourceSearchBase -SearchScope Subtree -Filter * -Properties $groupProps)
        foreach ($g in $groups) {
            foreach ($mDn in @($g.Member)) {
                $obj = Get-ADObject @SourceParams -Identity $mDn -Properties @("Name", "ObjectClass")
                $memberRows += [PSCustomObject]@{
                    GroupDn           = $g.DistinguishedName
                    GroupName         = $g.Name
                    MemberDn          = $mDn
                    MemberName        = $obj.Name
                    MemberObjectClass = $obj.ObjectClass
                }
            }
        }
    }

    Write-Host ("    OUs: " + $ous.Count + "  Users: " + $users.Count + "  Groups: " + $groups.Count) -ForegroundColor Green

    if ($SaveCsv -ne "") {
        New-Item -ItemType Directory -Force -Path $SaveCsv | Out-Null
        $ous | Select-Object Name, Description, DistinguishedName |
            Export-Csv (Join-Path $SaveCsv "ous.csv") -NoTypeInformation -Encoding UTF8
        $users | Select-Object SamAccountName, UserPrincipalName, DisplayName, GivenName, Surname,
            EmailAddress, Title, Department, Description, Enabled, DistinguishedName |
            Export-Csv (Join-Path $SaveCsv "users.csv") -NoTypeInformation -Encoding UTF8
        if ($groups.Count -gt 0) {
            $groups | Select-Object Name, Description, GroupCategory, GroupScope, DistinguishedName |
                Export-Csv (Join-Path $SaveCsv "groups.csv") -NoTypeInformation -Encoding UTF8
            $memberRows | Export-Csv (Join-Path $SaveCsv "group-members.csv") -NoTypeInformation -Encoding UTF8
        }
        Write-Host ("    CSV backup: " + $SaveCsv) -ForegroundColor DarkGray
    }

    return @{
        OUs        = $ous
        Users      = $users
        Groups     = $groups
        MemberRows = $memberRows
    }
}

function Write-TargetSubtree {
    param(
        [hashtable] $Data,
        [hashtable] $TargetParams,
        [bool] $PreviewOnly
    )

    Write-Host (">>> [2/2] Write to test domain: " + $TargetDomainSuffix) -ForegroundColor Cyan
    if ($PreviewOnly) {
        Write-Host "    WhatIf mode - no changes will be made" -ForegroundColor Yellow
    }

    $securePwd = ConvertTo-SecureString $DefaultPassword -AsPlainText -Force
    $userBySourceDn = @{}
    foreach ($u in $Data.Users) {
        $userBySourceDn[$u.DistinguishedName] = $u
    }

    $chain = @($TargetRootOu, $AiTechOuDn)
    foreach ($dn in $chain) {
        $namePart = ($dn -split "=", 2)[1]
        $name = $namePart
        if ($namePart -match ",") { $name = ($namePart -split ",")[0] }
        $parent = Get-ParentDn $dn
        $filter = "distinguishedName -eq '" + $dn + "'"
        $existing = Get-ADOrganizationalUnit @TargetParams -Filter $filter -ErrorAction SilentlyContinue
        if ($existing) { continue }
        Write-Host ("[OU] Create " + $dn)
        if (-not $PreviewOnly) {
            New-ADOrganizationalUnit @TargetParams -Name $name -Path $parent -ProtectedFromAccidentalDeletion $false
        }
    }

    $skipDns = @($TargetRootOu, $AiTechOuDn)
    $sortedOus = $Data.OUs | Sort-Object { Get-OuDepth $_.DistinguishedName }
    foreach ($ou in $sortedOus) {
        $targetDn = ConvertTo-TargetDn $ou.DistinguishedName
        if ($skipDns -contains $targetDn) { continue }
        $filter = "distinguishedName -eq '" + $targetDn + "'"
        $existing = Get-ADOrganizationalUnit @TargetParams -Filter $filter -ErrorAction SilentlyContinue
        if ($existing) { continue }
        $namePart = ($targetDn -split "=", 2)[1]
        $name = $namePart
        if ($namePart -match ",") { $name = ($namePart -split ",")[0] }
        $parent = Get-ParentDn $targetDn
        Write-Host ("[OU] Create " + $targetDn)
        if (-not $PreviewOnly) {
            New-ADOrganizationalUnit @TargetParams -Name $name -Path $parent -Description $ou.Description `
                -ProtectedFromAccidentalDeletion $false
        }
    }

    foreach ($u in $Data.Users) {
        $sam = $u.SamAccountName + $SamAccountSuffix
        $targetParent = Get-ParentDn (ConvertTo-TargetDn $u.DistinguishedName)
        $upn = $sam + "@dltornado2.com"
        $mail = $sam + "@dltornado2.com"

        $filter = "sAMAccountName -eq '" + $sam + "'"
        $existingUser = Get-ADUser @TargetParams -Filter $filter -ErrorAction SilentlyContinue
        if ($existingUser) {
            Write-Host ("[User] Skip existing: " + $sam) -ForegroundColor DarkGray
            continue
        }

        Write-Host ("[User] Create " + $sam + " (" + $u.DisplayName + ") -> " + $targetParent)
        if ($PreviewOnly) { continue }

        New-ADUser @TargetParams `
            -SamAccountName $sam `
            -UserPrincipalName $upn `
            -Name $u.DisplayName `
            -DisplayName $u.DisplayName `
            -Path $targetParent `
            -AccountPassword $securePwd `
            -Enabled $u.Enabled `
            -ChangePasswordAtLogon $false
        if ($u.GivenName) { Set-ADUser -Identity $sam @TargetParams -GivenName $u.GivenName }
        if ($u.Surname) { Set-ADUser -Identity $sam @TargetParams -Surname $u.Surname }
        if ($u.Title) { Set-ADUser -Identity $sam @TargetParams -Title $u.Title }
        if ($u.Department) { Set-ADUser -Identity $sam @TargetParams -Department $u.Department }
        if ($u.Description) { Set-ADUser -Identity $sam @TargetParams -Description $u.Description }
        Set-ADUser -Identity $sam @TargetParams -EmailAddress $mail
    }

    if ($SkipGroups -or $Data.Groups.Count -eq 0) {
        return
    }

    foreach ($g in $Data.Groups) {
        $groupSam = ($g.Name -replace "\s", "") + $SamAccountSuffix
        if ($groupSam.Length -gt 20) {
            $groupSam = $groupSam.Substring(0, 20)
        }
        $parent = Get-ParentDn (ConvertTo-TargetDn $g.DistinguishedName)

        $filter = "sAMAccountName -eq '" + $groupSam + "'"
        $existingGroup = Get-ADGroup @TargetParams -Filter $filter -ErrorAction SilentlyContinue
        if ($existingGroup) {
            Write-Host ("[Group] Skip existing: " + $groupSam) -ForegroundColor DarkGray
            continue
        }
        Write-Host ("[Group] Create " + $g.Name + " (sAMAccountName=" + $groupSam + ")")
        if ($PreviewOnly) { continue }

        New-ADGroup @TargetParams `
            -Name $g.Name `
            -SamAccountName $groupSam `
            -GroupCategory $g.GroupCategory `
            -GroupScope $g.GroupScope `
            -Path $parent `
            -Description $g.Description
    }

    foreach ($row in $Data.MemberRows) {
        if ($row.MemberObjectClass -ne "user") { continue }

        $userRow = $userBySourceDn[$row.MemberDn]
        if (-not $userRow) {
            $cnPart = ($row.MemberDn -split ",")[0]
            $cn = $cnPart -replace "^CN=", ""
            $userRow = $Data.Users | Where-Object {
                $_.DisplayName -eq $cn -or $_.SamAccountName -eq $cn
            } | Select-Object -First 1
        }
        if (-not $userRow) {
            Write-Host ("[Group] Skip member: " + $row.MemberName + " in " + $row.GroupName) -ForegroundColor DarkGray
            continue
        }

        $groupSam = ($row.GroupName -replace "\s", "") + $SamAccountSuffix
        if ($groupSam.Length -gt 20) {
            $groupSam = $groupSam.Substring(0, 20)
        }
        $memberSam = $userRow.SamAccountName + $SamAccountSuffix

        $gf = "sAMAccountName -eq '" + $groupSam + "'"
        $uf = "sAMAccountName -eq '" + $memberSam + "'"
        $group = Get-ADGroup @TargetParams -Filter $gf -ErrorAction SilentlyContinue
        $user = Get-ADUser @TargetParams -Filter $uf -ErrorAction SilentlyContinue
        if (-not $group -or -not $user) { continue }

        $members = @(Get-ADGroupMember @TargetParams -Identity $group)
        $already = $false
        foreach ($m in $members) {
            if ($m.DistinguishedName -eq $user.DistinguishedName) {
                $already = $true
                break
            }
        }
        if ($already) { continue }

        Write-Host ("[Group] Add " + $memberSam + " -> " + $groupSam)
        if (-not $PreviewOnly) {
            Add-ADGroupMember @TargetParams -Identity $group -Members $user
        }
    }
}

Ensure-ADModule

if (-not $SourceCredential) {
    $SourceCredential = Get-Credential -Message ("Production " + $SourceServer + " (use MYWIND\user or user@mywind.com.cn)")
}
if (-not $TargetCredential) {
    $TargetCredential = Get-Credential -Message ("Test " + $TargetServer + " (use DLTORNADO2\user or user@dltornado2.com)")
}

$SourceCredential = Normalize-DomainCredential -Credential $SourceCredential -NetBiosDomain $SourceDomainNetbios -UpnSuffix $SourceServer
$TargetCredential = Normalize-DomainCredential -Credential $TargetCredential -NetBiosDomain $TargetDomainNetbios -UpnSuffix $TargetServer

$resolvedSourceDc = Resolve-DomainController -DomainName $SourceServer -PreferredDc $SourceDc -Credential $SourceCredential
$resolvedTargetDc = Resolve-DomainController -DomainName $TargetServer -PreferredDc $TargetDc -Credential $TargetCredential

$sourceParams = Get-ServerParams -Server $resolvedSourceDc -Credential $SourceCredential
$targetParams = Get-ServerParams -Server $resolvedTargetDc -Credential $TargetCredential

Write-Host ""
Write-Host "AD Sync: AI Tech Center (production -> test)" -ForegroundColor White
Write-Host ("  Source domain: " + $SourceServer + "  DC: " + $resolvedSourceDc)
Write-Host ("  Target domain: " + $TargetServer + "  DC: " + $resolvedTargetDc + "  -> myse\IT")
Write-Host ""

Test-ADConnection -Label "production" -ServerParams $sourceParams -SearchBase $SourceSearchBase
# Test against existing OU=IT (target subtree may not exist yet on first run)
Test-ADConnection -Label "test" -ServerParams $targetParams -SearchBase $TargetDomainSuffix

$data = Read-SourceSubtree -SourceParams $sourceParams
$preview = $false
if ($WhatIf) { $preview = $true }
Write-TargetSubtree -Data $data -TargetParams $targetParams -PreviewOnly $preview

Write-Host ""
if ($WhatIf) {
    Write-Host "WhatIf done. Run again without -WhatIf to apply." -ForegroundColor Yellow
}
else {
    Write-Host "Sync completed." -ForegroundColor Green
    Write-Host ("Login: sAMAccountName" + $SamAccountSuffix + "@dltornado2.com")
}

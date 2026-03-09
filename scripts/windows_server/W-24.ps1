$result=0

$network = Get-NetIPInterface | Select-Object InterfaceAlias, AddressFamily, ConnectionState, InterfaceIndex, Dhcp
$netBIOS = Get-WmiObject -Query "SELECT * FROM Win32_NetworkAdapterConfiguration WHERE IPEnabled = True" | Select-Object Description, SettingID, IPEnabled, TcpipNetbiosOptions

if($netBIOS.TcpipNetbiosOptions -ne 1) {
    Write-Host "$($netBIOS.Description) 네트워크와 바인딩 되어 있습니다. 설정값: $($netBIOS.TcpipNetbiosOptions)"
    $result += 1
}

Write-Host "점검 결과: $result"
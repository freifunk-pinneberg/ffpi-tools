#!/bin/sh
set -e

GATE=$(hostname)
IFACES=$(ls /var/lib/vnstat/)

TARGET=/var/www/html/

for iface in $IFACES; do
    /usr/bin/vnstati -i ${iface} -h -o ${TARGET}${iface}_hourly.png
    /usr/bin/vnstati -i ${iface} -d -o ${TARGET}${iface}_daily.png
    /usr/bin/vnstati -i ${iface} -m -o ${TARGET}${iface}_monthly.png
    /usr/bin/vnstati -i ${iface} -t -o ${TARGET}${iface}_top10.png
    /usr/bin/vnstati -i ${iface} -s -o ${TARGET}${iface}_summary.png
done

cat > ${TARGET}index.html <<EOT
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"
    "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">

<html xmlns="http://www.w3.org/1999/xhtml" lang="en" xml:lang="en">
<head>
  <title>$GATE - Network Traffic</title>
  <meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
  <meta http-equiv="Content-Language" content="en" />
</head>

<body style="white-space: nowrap">
EOT

for iface in $IFACES; do
    sed s/IFACE/${iface}/g >> ${TARGET}index.html <<EOT
    <div style="display:inline-block;vertical-align: top">
    <img src="IFACE_summary.png" alt="traffic summary" /><br>
    <img src="IFACE_monthly.png" alt="traffic per month" /><br>
    <img src="IFACE_hourly.png" alt="traffic per hour" /><br>
    <img src="IFACE_top10.png" alt="traffic top10" /><br>
    <img src="IFACE_daily.png" alt="traffic per day" />
    </div>
EOT

done

echo "</body></html>" >> ${TARGET}index.html

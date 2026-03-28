<?php
/** Check local dmsedu_db for 2030+ schedules.
 *  Requires env vars: DMS_LOCAL_HOST, DMS_LOCAL_PORT, DMS_LOCAL_USER, DMS_LOCAL_PASSWORD, DMS_LOCAL_DATABASE
 *  Usage: DMS_LOCAL_HOST=127.0.0.1 DMS_LOCAL_PORT=3307 DMS_LOCAL_USER=root DMS_LOCAL_PASSWORD="" DMS_LOCAL_DATABASE=dmsedu_db php scripts/check_local_2030.php
 */
$host     = getenv('DMS_LOCAL_HOST')     ?: '127.0.0.1';
$port     = getenv('DMS_LOCAL_PORT')     ?: '3307';
$user     = getenv('DMS_LOCAL_USER')     ?: 'root';
$password = getenv('DMS_LOCAL_PASSWORD');
$database = getenv('DMS_LOCAL_DATABASE') ?: 'dmsedu_db';

$conn = new mysqli($host, $user, $password, $database, (int)$port);
if ($conn->connect_error) { echo 'Error: ' . $conn->connect_error; exit(1); }

echo "=== schedule_follow_up (2030+) ===" . PHP_EOL;
$r1 = $conn->query("SELECT sf.id, sf.id_univ, sf.jadwal_audiensi, sf.est_audiens FROM schedule_follow_up sf WHERE sf.jadwal_audiensi >= '2030-01-01' ORDER BY sf.jadwal_audiensi");
echo "Count: " . $r1->num_rows . PHP_EOL;
while ($row = $r1->fetch_assoc()) {
    echo "  ID={$row['id']} univ={$row['id_univ']} date={$row['jadwal_audiensi']} audiens={$row['est_audiens']}" . PHP_EOL;
}

echo PHP_EOL . "=== request_surat_audiensi_detail (2030+) ===" . PHP_EOL;
$r2 = $conn->query("SELECT d.id, d.id_univ, d.tanggal_audiensi, d.status_surat, d.nomor_surat, d.nama_penerima, u.universitas FROM request_surat_audiensi_detail d LEFT JOIN universitas u ON d.id_univ = u.id_univ WHERE d.tanggal_audiensi >= '2030-01-01' ORDER BY d.tanggal_audiensi");
echo "Count: " . $r2->num_rows . PHP_EOL;
while ($row = $r2->fetch_assoc()) {
    echo "  ID={$row['id']} univ={$row['id_univ']} date={$row['tanggal_audiensi']} status={$row['status_surat']} surat={$row['nomor_surat']} univ_name={$row['universitas']}" . PHP_EOL;
}

$conn->close();

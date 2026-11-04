// Logika Client-Side Web App Presensi Ekskul MTs Muhammadiyah Tajurhalang

let currentSiswaList = [];
let attendanceState = {}; // { siswaId: 'Hadir' | 'Izin' | 'Sakit' | 'Alpa' }

document.addEventListener('DOMContentLoaded', () => {
    // Set default jam latihan ke waktu sekarang
    const now = new Date();
    const hours = String(now.getHours()).padStart(2, '0');
    const minutes = String(now.getMinutes()).padStart(2, '0');
    const jamInput = document.getElementById('jamLatihan');
    if (jamInput) jamInput.value = `${hours}:${minutes}`;

    // Otomatis cek lokasi saat aplikasi dibuka
    checkUserLocation(false);
});

// 1. Cek Lokasi Geolocation GPS HP
function checkUserLocation(isManualClick = false) {
    const badge = document.getElementById('gpsBadge');
    const badgeIcon = document.getElementById('gpsBadgeIcon');
    const badgeText = document.getElementById('gpsBadgeText');
    const details = document.getElementById('gpsDetails');
    const distanceEl = document.getElementById('gpsDistance');
    const noteEl = document.getElementById('gpsNote');

    if (!navigator.geolocation) {
        badge.className = 'gps-badge invalid';
        badgeIcon.innerText = '⚠️';
        badgeText.innerText = 'Browser HP tidak mendukung GPS';
        noteEl.innerText = 'Silakan gunakan browser modern (Chrome / Safari).';
        return;
    }

    badge.className = 'gps-badge';
    badgeIcon.innerText = '⏳';
    badgeText.innerText = 'Mengunci koordinat GPS HP...';

    navigator.geolocation.getCurrentPosition(
        async (position) => {
            const lat = position.coords.latitude;
            const lng = position.coords.longitude;

            document.getElementById('userLat').value = lat;
            document.getElementById('userLng').value = lng;

            try {
                const response = await fetch('/api/lokasi/cek', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ latitude: lat, longitude: lng })
                });
                const res = await response.json();

                details.style.display = 'flex';
                distanceEl.innerText = `${res.jarak_meter} meter`;
                document.getElementById('userDistance').value = res.jarak_meter;

                if (res.is_valid) {
                    badge.className = 'gps-badge valid';
                    badgeIcon.innerText = '🟢';
                    badgeText.innerText = `Lokasi Valid! Anda berada di area lapangan madrasah (${res.jarak_meter}m).`;
                    document.getElementById('userLocStatus').value = 'VALID';
                    noteEl.innerText = `Koordinat terverifikasi di radius ${res.radius_meter}m dari ${res.nama_lokasi}.`;
                } else {
                    badge.className = 'gps-badge invalid';
                    badgeIcon.innerText = '🔴';
                    badgeText.innerText = `Di Luar Radius Lapangan (${res.jarak_meter}m dari titik pusat).`;
                    document.getElementById('userLocStatus').value = 'DILUAR_AREA';
                    noteEl.innerText = `Batas toleransi adalah ${res.radius_meter}m. Pastikan Anda berada di area MTs Muhammadiyah Tajurhalang.`;
                }
            } catch (err) {
                badge.className = 'gps-badge invalid';
                badgeIcon.innerText = '⚠️';
                badgeText.innerText = 'Gagal verifikasi jarak ke server.';
            }
        },
        (error) => {
            badge.className = 'gps-badge invalid';
            badgeIcon.innerText = '❌';
            if (error.code === error.PERMISSION_DENIED) {
                badgeText.innerText = 'Izin lokasi (GPS) ditolak oleh pengguna.';
                noteEl.innerText = 'Ketuk ikon gembok di browser HP lalu izinkan akses "Lokasi" agar presensi terverifikasi.';
            } else {
                badgeText.innerText = 'Gagal membaca GPS: ' + error.message;
            }
            // Tetap izinkan input jika darurat
            document.getElementById('userLocStatus').value = 'GPS_OFF';
        },
        { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
    );
}

// 2. Event saat cabang Ekskul dipilih
async function onEkskulChange() {
    const select = document.getElementById('selectEkskul');
    const selectedOpt = select.options[select.selectedIndex];
    const ekskulId = select.value;

    if (!ekskulId) return;

    // Isi nama pelatih otomatis jika kosong
    const pelatihDefault = selectedOpt.getAttribute('data-pelatih');
    const pelatihInput = document.getElementById('namaPelatih');
    if (pelatihDefault && (!pelatihInput.value || pelatihInput.getAttribute('data-auto') === 'true')) {
        pelatihInput.value = pelatihDefault;
        pelatihInput.setAttribute('data-auto', 'true');
    }

    pelatihInput.addEventListener('input', () => {
        pelatihInput.removeAttribute('data-auto');
    });

    // Ambil daftar siswa anggota ekskul ini
    try {
        const res = await fetch(`/api/ekskul/${ekskulId}/siswa`);
        const data = await res.json();
        currentSiswaList = data.siswa || [];

        // Reset attendance state: default semua HADIR
        attendanceState = {};
        currentSiswaList.forEach(s => {
            attendanceState[s.id] = 'Hadir';
        });

        // Tampilkan container
        document.getElementById('rosterCard').style.display = 'block';
        document.getElementById('submitBar').style.display = 'block';
        document.getElementById('rosterTitle').innerText = `👥 Anggota ${data.ekskul.icon} ${data.ekskul.nama} (${currentSiswaList.length} Siswa)`;

        renderStudentList();
        updateSummaryCounters();
    } catch (err) {
        alert("Gagal memuat data siswa: " + err.message);
    }
}

// 3. Render daftar siswa ke layar
function renderStudentList(filterText = '') {
    const container = document.getElementById('studentListContainer');
    container.innerHTML = '';

    const filtered = currentSiswaList.filter(s => 
        s.nama.toLowerCase().includes(filterText.toLowerCase()) || 
        s.kelas.toLowerCase().includes(filterText.toLowerCase())
    );

    if (filtered.length === 0) {
        container.innerHTML = `<div style="text-align:center; padding:15px; color:#64748B;">Tidak ada siswa yang cocok.</div>`;
        return;
    }

    filtered.forEach(s => {
        const currentStatus = attendanceState[s.id] || 'Hadir';

        const row = document.createElement('div');
        row.className = 'student-row';
        row.innerHTML = `
            <div class="student-info">
                <span class="student-name">${s.nama}</span>
                <span class="student-meta">${s.kelas} • (${s.jenis_kelamin})</span>
            </div>
            <div class="att-buttons">
                <button type="button" class="btn-att ${currentStatus === 'Hadir' ? 'active-H' : ''}" 
                        onclick="setAttendance(${s.id}, 'Hadir')">H</button>
                <button type="button" class="btn-att ${currentStatus === 'Izin' ? 'active-I' : ''}" 
                        onclick="setAttendance(${s.id}, 'Izin')">I</button>
                <button type="button" class="btn-att ${currentStatus === 'Sakit' ? 'active-S' : ''}" 
                        onclick="setAttendance(${s.id}, 'Sakit')">S</button>
                <button type="button" class="btn-att ${currentStatus === 'Alpa' ? 'active-A' : ''}" 
                        onclick="setAttendance(${s.id}, 'Alpa')">A</button>
            </div>
        `;
        container.appendChild(row);
    });
}

// 4. Ubah status kehadiran siswa
function setAttendance(siswaId, status) {
    attendanceState[siswaId] = status;
    renderStudentList(document.getElementById('searchSiswa').value);
    updateSummaryCounters();
}

// 5. Set semua siswa ke suatu status
function setAllAttendance(status) {
    currentSiswaList.forEach(s => {
        attendanceState[s.id] = status;
    });
    renderStudentList(document.getElementById('searchSiswa').value);
    updateSummaryCounters();
}

// 6. Filter pencarian siswa
function filterSiswa() {
    const text = document.getElementById('searchSiswa').value;
    renderStudentList(text);
}

// 7. Update counter hadir, izin, sakit, alpa
function updateSummaryCounters() {
    let hadir = 0, izin = 0, sakit = 0, alpa = 0;
    Object.values(attendanceState).forEach(st => {
        if (st === 'Hadir') hadir++;
        else if (st === 'Izin') izin++;
        else if (st === 'Sakit') sakit++;
        else if (st === 'Alpa') alpa++;
    });

    document.getElementById('countHadir').innerText = hadir;
    document.getElementById('countIzin').innerText = izin;
    document.getElementById('countSakit').innerText = sakit;
    document.getElementById('countAlpa').innerText = alpa;
}

// 8. Submit Presensi ke Server
async function submitPresensi() {
    const ekskulId = document.getElementById('selectEkskul').value;
    const namaPelatih = document.getElementById('namaPelatih').value.trim();
    const jamMulai = document.getElementById('jamLatihan').value;
    const materiLatihan = document.getElementById('materiLatihan').value.trim();
    const catatan = document.getElementById('catatanLatihan').value.trim();

    const lat = document.getElementById('userLat').value;
    const lng = document.getElementById('userLng').value;
    const distance = document.getElementById('userDistance').value;
    const locStatus = document.getElementById('userLocStatus').value;

    if (!ekskulId || !namaPelatih) {
        alert("Mohon pilih cabang ekskul dan isi nama pelatih!");
        return;
    }

    if (currentSiswaList.length === 0) {
        alert("Belum ada data siswa untuk cabang ekskul ini.");
        return;
    }

    const presensiArray = currentSiswaList.map(s => ({
        siswa_id: s.id,
        status_kehadiran: attendanceState[s.id] || 'Hadir',
        keterangan: ''
    }));

    const btnSubmit = document.getElementById('btnSubmit');
    btnSubmit.disabled = true;
    btnSubmit.innerText = "⏳ Sedang Menyimpan Presensi...";

    const payload = {
        ekskul_id: parseInt(ekskulId),
        nama_pelatih: namaPelatih,
        jam_mulai: jamMulai,
        materi_latihan: materiLatihan,
        catatan: catatan,
        latitude: parseFloat(lat),
        longitude: parseFloat(lng),
        presensi_siswa: presensiArray
    };

    try {
        const res = await fetch('/api/presensi/simpan', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const result = await res.json();

        btnSubmit.disabled = false;
        btnSubmit.innerText = "💾 Simpan & Rekap Presensi Latihan";

        if (result.status === 'SUCCESS') {
            document.getElementById('modalSuccessMsg').innerText = 
                `Presensi ${namaPelatih} & ${presensiArray.length} siswa berhasil disimpan. Terverifikasi lokasi: ${locStatus} (${distance}m).`;
            document.getElementById('modalSuccess').style.display = 'flex';
        } else {
            alert("Gagal: " + result.pesan);
        }
    } catch (err) {
        btnSubmit.disabled = false;
        btnSubmit.innerText = "💾 Simpan & Rekap Presensi Latihan";
        alert("Terjadi kesalahan koneksi: " + err.message);
    }
}

function closeModal() {
    document.getElementById('modalSuccess').style.display = 'none';
}

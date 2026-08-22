"""
PDF Generator for Exam Results and Certificates
Uses ReportLab for professional PDF generation.
"""
from io import BytesIO
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, letter, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch, cm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, Image, PageBreak
    )
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


class ExamResultPDF:
    """Generate PDF for exam results."""

    SCHOOL_NAME = "MADRASAH ALIYAH NEGERI 1 ROKAN HULU"
    SCHOOL_SUBTITLE = "Laporan Resmi Hasil Asesmen SIAB1"

    def __init__(self):
        if not REPORTLAB_AVAILABLE:
            raise ImportError("ReportLab not installed. Run: pip install reportlab")
        self.styles = getSampleStyleSheet()
        self.logo_path = self._resolve_logo_path()
        self._create_custom_styles()

    def _resolve_logo_path(self) -> Optional[str]:
        base_dir = Path(__file__).resolve().parents[2]
        candidates = [
            base_dir / "static" / "uploads" / "logo-man1.jpeg",
            base_dir / "tools" / "logoman1.jpeg",
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return None

    def _create_custom_styles(self):
        """Create custom paragraph styles."""
        self.styles.add(ParagraphStyle(
            name='SchoolName',
            parent=self.styles['Heading1'],
            fontSize=16,
            spaceAfter=2,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#0f172a')
        ))
        self.styles.add(ParagraphStyle(
            name='SchoolSubtitle',
            parent=self.styles['Normal'],
            fontSize=10,
            spaceAfter=10,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#334155')
        ))
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Title'],
            fontSize=24,
            spaceAfter=30,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#1a365d')
        ))

        self.styles.add(ParagraphStyle(
            name='CustomHeading',
            parent=self.styles['Heading2'],
            fontSize=14,
            spaceBefore=20,
            spaceAfter=10,
            textColor=colors.HexColor('#2c5282')
        ))

        self.styles.add(ParagraphStyle(
            name='InfoText',
            parent=self.styles['Normal'],
            fontSize=11,
            spaceAfter=5
        ))

    def _clean_text(self, text: Any) -> str:
        """Sanitize text for PDF generation (handle unicode)."""
        if text is None:
            return ""
        text = str(text)
        # Replace problematic characters that standard fonts can't handle
        # Keep basic latin, numbers, punctuation
        return text.encode('latin-1', 'replace').decode('latin-1')

    def generate(
        self,
        exam_title: str,
        exam_date: str,
        results: List[Dict[str, Any]],
        summary: Dict[str, Any],
        creator_name: Optional[str] = None
    ) -> bytes:
        """
        Generate exam results PDF.
        """
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=2*cm,
            leftMargin=2*cm,
            topMargin=2*cm,
            bottomMargin=2*cm
        )

        story = []

        # Clean inputs
        exam_title = self._clean_text(exam_title)
        creator_name = self._clean_text(creator_name)

        # Add Header Line (Kop Surat Effect)
        if self.logo_path:
            logo = Image(self.logo_path, width=2.2 * cm, height=2.2 * cm)
            logo.hAlign = 'CENTER'
            story.append(logo)
            story.append(Spacer(1, 4))
        story.append(Paragraph(self.SCHOOL_NAME, self.styles['SchoolName']))
        story.append(Paragraph(self.SCHOOL_SUBTITLE, self.styles['SchoolSubtitle']))
        story.append(Paragraph("LAPORAN HASIL UJIAN",
            ParagraphStyle(name='ReportTitle', parent=self.styles['Normal'], alignment=TA_CENTER, fontSize=12, spaceAfter=10, textColor=colors.HexColor('#166534'))))
        story.append(HRFlowable(width="100%", thickness=2, color=colors.black, spaceAfter=20))

        # Title Block
        story.append(Paragraph(f"JUDUL: {exam_title}", self.styles['CustomHeading']))
        story.append(Spacer(1, 10))

        # Exam info Table (Metadata)
        meta_data = [
            ['Tanggal Pelaksanaan', f': {exam_date}'],
            ['Guru Pelaksana', f': {creator_name or "-"}'],
            ['Total Peserta', f': {len(results)} Siswa']
        ]
        meta_table = Table(meta_data, colWidths=[120, 300], hAlign='LEFT')
        meta_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 20))

        # Summary statistics
        story.append(Paragraph("Ringkasan Statistik", self.styles['CustomHeading'])) # Removed emoji

        summary_data = [
            ['Statistik', 'Nilai'],
            ['Rata-rata', f"{summary.get('average', 0):.2f}"],
            ['Nilai Tertinggi', f"{summary.get('highest', 0):.2f}"],
            ['Nilai Terendah', f"{summary.get('lowest', 0):.2f}"],
            ['Lulus', f"{summary.get('passed', 0)} ({summary.get('pass_rate', 0):.1f}%)"],
            ['Tidak Lulus', f"{summary.get('failed', 0)}"],
        ]

        summary_table = Table(summary_data, colWidths=[200, 150])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f2937')), # Darker header
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black), # Explicit black grid
            ('FONTSIZE', (0, 1), (-1, -1), 10),
        ]))
        story.append(summary_table)
        story.append(Spacer(1, 30))

        # Results table
        story.append(Paragraph("Daftar Nilai Peserta", self.styles['CustomHeading'])) # Removed emoji

        # Prepare table data
        table_data = [['No', 'Nama Peserta', 'Kelas', 'Skor', 'Status']]
        for i, result in enumerate(results, 1):
            status = "Lulus" if result.get('passed', False) else "Tidak Lulus"
            table_data.append([
                str(i),
                self._clean_text(result.get('student_name', 'N/A')),
                self._clean_text(result.get('student_class', '-')),
                f"{result.get('score', 0):.1f}",
                status
            ])

        # Auto-calculate available width (A4 width - margins)
        # A4 = 21cm width. Margins 2cm left/right. Content = 17cm.
        # Approx points: 1cm = 28.35pt. 17cm = 481pt.
        results_table = Table(table_data, colWidths=[30, 200, 80, 60, 100])
        results_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f2937')), # Professional Dark Grey/Blue
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'), # Center headers
            ('ALIGN', (1, 1), (1, -1), 'LEFT'),    # Left align names
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            # Professional Grid
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('BOX', (0, 0), (-1, -1), 1, colors.black), # Outer box thicker

            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('TOPPADDING', (0, 1), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f3f4f6')]), # Subtle zebra
        ]))
        story.append(results_table)

        # Footer
        story.append(Spacer(1, 40))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#e2e8f0')))
        story.append(Spacer(1, 10))
        story.append(Paragraph(
            f"<i>Dokumen ini dihasilkan secara otomatis pada {datetime.now().strftime('%d %B %Y, %H:%M')}</i>",
            ParagraphStyle(name='Footer', fontSize=8, textColor=colors.gray, alignment=TA_CENTER)
        ))

        doc.build(story)
        return buffer.getvalue()


class CertificatePDF:
    """Generate certificate PDF for exam completion."""

    def __init__(self):
        if not REPORTLAB_AVAILABLE:
            raise ImportError("ReportLab not installed. Run: pip install reportlab")
        self.styles = getSampleStyleSheet()

    def generate(
        self,
        student_name: str,
        exam_title: str,
        score: float,
        completion_date: str,
        certificate_id: str,
        institution_name: str = "SIAB1"
    ) -> bytes:
        """
        Generate certificate PDF.

        Returns:
            PDF as bytes
        """
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=1*inch,
            leftMargin=1*inch,
            topMargin=1*inch,
            bottomMargin=1*inch
        )

        story = []

        # Helper to clean text
        def clean(text):
            if text is None: return ""
            return str(text).encode('latin-1', 'replace').decode('latin-1')

        student_name = clean(student_name)
        exam_title = clean(exam_title)
        institution_name = clean(institution_name)

        # Certificate styles
        title_style = ParagraphStyle(
            name='CertTitle',
            fontSize=36,
            alignment=TA_CENTER,
            spaceAfter=30,
            textColor=colors.HexColor('#1a365d'),
            fontName='Helvetica-Bold'
        )

        subtitle_style = ParagraphStyle(
            name='CertSubtitle',
            fontSize=14,
            alignment=TA_CENTER,
            spaceAfter=20,
            textColor=colors.HexColor('#4a5568')
        )

        name_style = ParagraphStyle(
            name='CertName',
            fontSize=28,
            alignment=TA_CENTER,
            spaceAfter=20,
            textColor=colors.HexColor('#2c5282'),
            fontName='Helvetica-Bold'
        )

        body_style = ParagraphStyle(
            name='CertBody',
            fontSize=12,
            alignment=TA_CENTER,
            spaceAfter=15,
            textColor=colors.HexColor('#4a5568')
        )

        # Decorative line
        story.append(HRFlowable(
            width="100%", thickness=3,
            color=colors.HexColor('#2c5282'),
            spaceAfter=30
        ))

        # Certificate content
        story.append(Spacer(1, 30))
        story.append(Paragraph("SERTIFIKAT", title_style))
        story.append(Paragraph("KELULUSAN UJIAN", subtitle_style))
        story.append(Spacer(1, 20))

        story.append(Paragraph("Diberikan kepada:", body_style))
        story.append(Paragraph(student_name, name_style))
        story.append(Spacer(1, 20))

        story.append(Paragraph(
            "Atas keberhasilannya menyelesaikan ujian:",
            body_style
        ))
        story.append(Paragraph(
            f"<b>{exam_title}</b>",
            ParagraphStyle(
                name='ExamTitle',
                fontSize=16,
                alignment=TA_CENTER,
                spaceAfter=20,
                textColor=colors.HexColor('#2c5282')
            )
        ))

        story.append(Spacer(1, 10))
        story.append(Paragraph(f"Dengan Skor: <b>{score:.1f}</b>", body_style))
        story.append(Paragraph(f"Tanggal: {completion_date}", body_style))
        story.append(Spacer(1, 40))

        # Signature area
        signature_data = [
            [institution_name, ''],
            ['_' * 30, ''],
            ['Administrator', ''],
        ]
        sig_table = Table(signature_data, colWidths=[200, 200])
        sig_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(sig_table)

        story.append(Spacer(1, 40))

        # Certificate ID
        story.append(HRFlowable(
            width="100%", thickness=3,
            color=colors.HexColor('#2c5282'),
            spaceBefore=20
        ))
        story.append(Paragraph(
            f"<i>Certificate ID: {certificate_id}</i>",
            ParagraphStyle(
                name='CertID',
                fontSize=8,
                alignment=TA_CENTER,
                textColor=colors.gray
            )
        ))

        doc.build(story)
        return buffer.getvalue()


class ViolationsReportPDF:
    """Generate PDF report for violation dashboard export."""

    SCHOOL_NAME = "MADRASAH ALIYAH NEGERI 1 ROKAN HULU"
    SCHOOL_SUBTITLE = "Laporan Resmi Monitoring Pelanggaran SIAB1"
    REPORT_CODE = "Dokumen internal pengawasan ujian"

    def __init__(self):
        if not REPORTLAB_AVAILABLE:
            raise ImportError("ReportLab not installed. Run: pip install reportlab")
        self.styles = getSampleStyleSheet()
        self.logo_path = self._resolve_logo_path()
        self._create_custom_styles()

    def _create_custom_styles(self):
        self.styles.add(ParagraphStyle(
            name='ViolationsTitle',
            parent=self.styles['Title'],
            fontSize=20,
            spaceAfter=10,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#111827')
        ))
        self.styles.add(ParagraphStyle(
            name='ViolationsSchool',
            parent=self.styles['Title'],
            fontSize=18,
            leading=22,
            spaceAfter=4,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#0f172a')
        ))
        self.styles.add(ParagraphStyle(
            name='ViolationsSubtitle',
            parent=self.styles['Heading2'],
            fontSize=11,
            leading=14,
            spaceAfter=4,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#334155')
        ))
        self.styles.add(ParagraphStyle(
            name='ViolationsBadge',
            parent=self.styles['Normal'],
            fontSize=9,
            leading=11,
            spaceAfter=8,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#166534')
        ))
        self.styles.add(ParagraphStyle(
            name='ViolationsSection',
            parent=self.styles['Heading2'],
            fontSize=12,
            spaceBefore=12,
            spaceAfter=8,
            textColor=colors.HexColor('#1f2937')
        ))
        self.styles.add(ParagraphStyle(
            name='ViolationsMeta',
            parent=self.styles['Normal'],
            fontSize=9,
            spaceAfter=4,
            textColor=colors.HexColor('#4b5563')
        ))
        self.styles.add(ParagraphStyle(
            name='ViolationsLead',
            parent=self.styles['BodyText'],
            fontSize=10,
            leading=14,
            spaceAfter=8,
            alignment=TA_LEFT,
            textColor=colors.HexColor('#1f2937')
        ))
        self.styles.add(ParagraphStyle(
            name='ViolationsSmall',
            parent=self.styles['BodyText'],
            fontSize=8.5,
            leading=11,
            spaceAfter=3,
            textColor=colors.HexColor('#475569')
        ))
        self.styles.add(ParagraphStyle(
            name='ViolationsCardText',
            parent=self.styles['BodyText'],
            fontSize=8.5,
            leading=11,
            spaceAfter=0,
            textColor=colors.HexColor('#1e293b')
        ))
        self.styles.add(ParagraphStyle(
            name='ViolationsMetricLabel',
            parent=self.styles['Normal'],
            fontSize=8.5,
            leading=10,
            spaceAfter=0,
            alignment=TA_LEFT,
            textColor=colors.white
        ))
        self.styles.add(ParagraphStyle(
            name='ViolationsMetricValue',
            parent=self.styles['Normal'],
            fontSize=19,
            leading=20,
            spaceAfter=0,
            alignment=TA_LEFT,
            textColor=colors.white
        ))

    def _resolve_logo_path(self) -> Optional[str]:
        candidate = Path(__file__).resolve().parents[2] / "tools" / "logoman1.jpeg"
        if candidate.exists():
            return str(candidate)
        return None

    def _clean_text(self, value: Any) -> str:
        if value is None:
            return ""
        return str(value).encode('latin-1', 'replace').decode('latin-1')

    def _format_decimal(self, value: Any) -> str:
        try:
            return f"{float(value):.2f}"
        except (TypeError, ValueError):
            return "0.00"

    def _resolve_risk(self, payload: Dict[str, Any]) -> Dict[str, str]:
        total_violations = int(payload.get('total_violations') or 0)
        unique_offenders = int(payload.get('unique_offender_count') or 0)
        top_type = next(iter(payload.get('type_breakdown') or []), {})
        top_severity = str(top_type.get('severity') or '').lower()

        if top_severity in {"critical", "high"} or total_violations >= 15 or unique_offenders >= 8:
            return {
                "label": "Tinggi",
                "message": "Perlu tindak lanjut cepat karena pola pelanggaran sudah cukup sering atau cukup berat.",
            }
        if total_violations >= 6 or unique_offenders >= 4:
            return {
                "label": "Perlu Perhatian",
                "message": "Pengawasan masih terkendali, tetapi perlu verifikasi lanjutan sebelum sesi berikutnya.",
            }
        return {
            "label": "Terkendali",
            "message": "Mayoritas kejadian masih terbatas dan cocok untuk ditangani lewat verifikasi rutin pengawas.",
        }

    def _build_metric_cards(self, payload: Dict[str, Any]) -> Table:
        cards = [
            ("Total Pelanggaran", self._clean_text(payload.get('total_violations', 0)), "#0f172a"),
            ("Pelanggar Unik", self._clean_text(payload.get('unique_offender_count', 0)), "#1d4ed8"),
            ("Rata-rata per Sesi", self._format_decimal(payload.get('average_per_session', 0)), "#166534"),
        ]
        metric_cells = []
        for label, value, _ in cards:
            cell = Table(
                [[Paragraph(self._clean_text(label), self.styles['ViolationsMetricLabel'])],
                 [Paragraph(self._clean_text(value), self.styles['ViolationsMetricValue'])]],
                colWidths=[224],
                rowHeights=[12, 22],
            )
            cell.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 0),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ]))
            metric_cells.append(cell)

        rows = [metric_cells]
        table = Table(rows, colWidths=[250, 250, 250])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, 0), colors.HexColor(cards[0][2])),
            ('BACKGROUND', (1, 0), (1, 0), colors.HexColor(cards[1][2])),
            ('BACKGROUND', (2, 0), (2, 0), colors.HexColor(cards[2][2])),
            ('BOX', (0, 0), (-1, -1), 0.7, colors.HexColor('#cbd5e1')),
            ('INNERGRID', (0, 0), (-1, -1), 0.7, colors.white),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 12),
            ('RIGHTPADDING', (0, 0), (-1, -1), 12),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        return table

    def _build_meta_table(
        self,
        period_text: str,
        exam_filter: str,
        generated_at: str,
        risk_snapshot: Dict[str, str],
    ) -> Table:
        rows = [
            ['Periode Laporan', period_text],
            ['Filter Ujian', exam_filter],
            ['Dibuat Pada', generated_at],
            ['Status Perhatian', risk_snapshot['label']],
        ]
        table = Table(rows, colWidths=[135, 290], hAlign='CENTER')
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e2e8f0')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#0f172a')),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.6, colors.HexColor('#cbd5e1')),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ]))
        return table

    def _build_management_summary(self, payload: Dict[str, Any], risk_snapshot: Dict[str, str]) -> str:
        top_type = next(iter(payload.get('type_breakdown') or []), {})
        top_offender = next(iter(payload.get('top_offenders') or []), {})
        type_label = self._clean_text(top_type.get('label') or 'belum ada jenis dominan')
        type_count = self._clean_text(top_type.get('count') or 0)
        offender_name = self._clean_text(top_offender.get('name') or 'belum ada peserta dominan')
        offender_count = self._clean_text(top_offender.get('count') or 0)
        return (
            f"Selama periode pemantauan ini, sistem mencatat <b>{self._clean_text(payload.get('total_violations', 0))}</b> "
            f"kejadian dari <b>{self._clean_text(payload.get('unique_offender_count', 0))}</b> peserta pada "
            f"<b>{self._clean_text(payload.get('affected_session_count', 0))}</b> sesi. "
            f"Jenis pelanggaran yang paling sering muncul adalah <b>{type_label}</b> sebanyak <b>{type_count}</b> kali. "
            f"Peserta dengan catatan terbanyak saat laporan dibuat adalah <b>{offender_name}</b> dengan "
            f"<b>{offender_count}</b> kejadian. Status pengawasan berada pada level <b>{risk_snapshot['label']}</b>, "
            f"yang berarti {self._clean_text(risk_snapshot['message']).lower()}"
        )

    def _build_cover_snapshot_table(self, payload: Dict[str, Any], risk_snapshot: Dict[str, str]) -> Table:
        top_type = next(iter(payload.get('type_breakdown') or []), {})
        top_offender = next(iter(payload.get('top_offenders') or []), {})
        rows = [[
            Paragraph(
                (
                    f"<b>Sorotan Utama</b><br/>"
                    f"{self._clean_text(top_type.get('label') or '-')} "
                    f"({self._clean_text(top_type.get('count') or 0)} kejadian)<br/>"
                    f"Peserta perlu dicek: {self._clean_text(top_offender.get('name') or '-')} "
                    f"({self._clean_text(top_offender.get('count') or 0)} kejadian)"
                ),
                self.styles['ViolationsCardText'],
            ),
            Paragraph(
                (
                    f"<b>Cakupan dan Tindak Lanjut</b><br/>"
                    f"{self._clean_text(payload.get('unique_exam_count', 0))} ujian | "
                    f"{self._clean_text(payload.get('affected_session_count', 0))} sesi terdampak<br/>"
                    f"{self._clean_text(risk_snapshot['message'])}"
                ),
                self.styles['ViolationsCardText'],
            ),
        ]]

        table = Table(rows, colWidths=[380, 380], hAlign='CENTER')
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
            ('BOX', (0, 0), (-1, -1), 0.6, colors.HexColor('#cbd5e1')),
            ('INNERGRID', (0, 0), (-1, -1), 0.6, colors.HexColor('#e2e8f0')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ]))
        return table

    def _build_explanation_cards(self, payload: Dict[str, Any]) -> Table:
        items = payload.get('type_breakdown') or []
        rows: List[List[Any]] = []
        current_row: List[Any] = []

        for item in items[:8]:
            explanation = item.get('explanation') or {}
            card = Paragraph(
                (
                    f"<b>{self._clean_text(item.get('label') or '-')}</b><br/>"
                    f"<font color='#334155'><b>Makna:</b> {self._clean_text(explanation.get('simple') or '-')}</font><br/>"
                    f"<font color='#334155'><b>Kenapa ditandai:</b> {self._clean_text(explanation.get('why') or '-')}</font><br/>"
                    f"<font color='#334155'><b>Analogi:</b> {self._clean_text(explanation.get('analogy') or '-')}</font>"
                ),
                self.styles['ViolationsCardText'],
            )
            current_row.append(card)
            if len(current_row) == 2:
                rows.append(current_row)
                current_row = []

        if current_row:
            current_row.append(Paragraph("", self.styles['ViolationsCardText']))
            rows.append(current_row)

        if not rows:
            rows = [[Paragraph("Belum ada data penjelasan pada periode ini.", self.styles['ViolationsCardText']), Paragraph("", self.styles['ViolationsCardText'])]]

        table = Table(rows, colWidths=[380, 380], hAlign='CENTER')
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.white),
            ('BOX', (0, 0), (-1, -1), 0.6, colors.HexColor('#cbd5e1')),
            ('INNERGRID', (0, 0), (-1, -1), 0.6, colors.HexColor('#e2e8f0')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 9),
            ('LEFTPADDING', (0, 0), (-1, -1), 9),
            ('RIGHTPADDING', (0, 0), (-1, -1), 9),
        ]))
        return table

    def _build_cover_page(
        self,
        story: List[Any],
        payload: Dict[str, Any],
        period_text: str,
        exam_filter: str,
        generated_at: str,
    ) -> None:
        risk_snapshot = self._resolve_risk(payload)

        story.append(HRFlowable(width="100%", thickness=1.4, color=colors.HexColor('#166534'), spaceAfter=5))
        if self.logo_path:
            logo = Image(self.logo_path, width=2.8 * cm, height=2.8 * cm)
            logo.hAlign = 'CENTER'
            story.append(logo)
            story.append(Spacer(1, 3))
        story.append(Paragraph(self.SCHOOL_NAME, self.styles['ViolationsSchool']))
        story.append(Paragraph(self.SCHOOL_SUBTITLE, self.styles['ViolationsSubtitle']))
        story.append(Paragraph(self.REPORT_CODE, self.styles['ViolationsBadge']))
        story.append(self._build_meta_table(period_text, exam_filter, generated_at, risk_snapshot))
        story.append(Spacer(1, 8))
        story.append(self._build_metric_cards(payload))
        story.append(Spacer(1, 8))
        story.append(Paragraph("Ringkasan Manajerial", self.styles['ViolationsSection']))
        story.append(Paragraph(
            self._build_management_summary(payload, risk_snapshot),
            self.styles['ViolationsLead'],
        ))
        story.append(Paragraph("Sorotan Cepat", self.styles['ViolationsSection']))
        story.append(self._build_cover_snapshot_table(payload, risk_snapshot))
        story.append(PageBreak())

    def _draw_footer(self, canvas, doc) -> None:
        canvas.saveState()
        width, _ = doc.pagesize
        canvas.setStrokeColor(colors.HexColor('#cbd5e1'))
        canvas.setLineWidth(0.5)
        canvas.line(doc.leftMargin, 0.95 * cm, width - doc.rightMargin, 0.95 * cm)
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.HexColor('#475569'))
        canvas.drawString(doc.leftMargin, 0.55 * cm, self._clean_text(self.SCHOOL_NAME))
        canvas.drawRightString(width - doc.rightMargin, 0.55 * cm, f"Halaman {doc.page}")
        canvas.restoreState()

    def _build_table(
        self,
        rows: List[List[Any]],
        col_widths: List[int],
        *,
        header_font_size: int = 8,
        body_font_size: float = 7,
        cell_padding: int = 4,
    ) -> Table:
        table = Table(rows, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#111827')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), header_font_size),
            ('FONTSIZE', (0, 1), (-1, -1), body_font_size),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#9ca3af')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), cell_padding),
            ('BOTTOMPADDING', (0, 0), (-1, -1), cell_padding),
            ('LEFTPADDING', (0, 0), (-1, -1), cell_padding),
            ('RIGHTPADDING', (0, 0), (-1, -1), cell_padding),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f3f4f6')]),
        ]))
        return table

    def generate(self, payload: Dict[str, Any]) -> bytes:
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            rightMargin=1.2 * cm,
            leftMargin=1.2 * cm,
            topMargin=1.2 * cm,
            bottomMargin=1.5 * cm,
        )
        story: List[Any] = []

        generated_at = self._clean_text(payload.get('generated_at_display') or payload.get('generated_at'))
        period_text = self._clean_text(payload.get('date_range_label', '-'))
        exam_filter = self._clean_text(payload.get('selected_exam_title') or 'Semua ujian')

        self._build_cover_page(story, payload, period_text, exam_filter, generated_at)

        summary_rows = [
            ['Metrik', 'Nilai'],
            ['Total Pelanggaran', self._clean_text(payload.get('total_violations', 0))],
            ['Pelanggar Unik', self._clean_text(payload.get('unique_offender_count', 0))],
            ['Ujian Terdampak', self._clean_text(payload.get('unique_exam_count', 0))],
            ['Sesi Terdampak', self._clean_text(payload.get('affected_session_count', 0))],
            ['Rata-rata per Sesi', self._clean_text(payload.get('average_per_session', 0))],
        ]
        story.append(Paragraph("Ringkasan Angka", self.styles['ViolationsTitle']))
        story.append(Paragraph(f"Periode: {period_text}", self.styles['ViolationsMeta']))
        story.append(Paragraph(f"Filter ujian: {exam_filter}", self.styles['ViolationsMeta']))
        story.append(Paragraph(f"Dibuat pada: {generated_at}", self.styles['ViolationsMeta']))
        story.append(HRFlowable(width="100%", thickness=1.1, color=colors.HexColor('#d1d5db'), spaceAfter=8))
        story.append(Paragraph("Ringkasan Statistik", self.styles['ViolationsSection']))
        story.append(self._build_table(summary_rows, [170, 110], body_font_size=7.5, cell_padding=5))
        story.append(Spacer(1, 10))

        offenders = payload.get('offender_details') or payload.get('top_offenders') or []
        offender_rows = [['No', 'Peserta', 'Kelas', 'Total', 'Pelanggaran Dominan', 'Terakhir']]
        for index, offender in enumerate(offenders[:10], start=1):
            dominant = (offender.get('type_breakdown') or [{}])[0]
            offender_rows.append([
                str(index),
                self._clean_text(f"{offender.get('name', '-')} (@{offender.get('username', '-')})"),
                self._clean_text(offender.get('class') or '-'),
                self._clean_text(offender.get('count', 0)),
                self._clean_text(dominant.get('label') or '-'),
                self._clean_text(offender.get('latest_violation_at_display') or '-'),
            ])
        story.append(Paragraph("Top Pelanggar", self.styles['ViolationsSection']))
        story.append(self._build_table(offender_rows, [28, 210, 58, 45, 110, 105], body_font_size=6.5, cell_padding=4))
        story.append(Spacer(1, 10))

        type_rows = [['Jenis Pelanggaran', 'Severity', 'Total', 'Pelanggar Unik', 'Peserta Dominan']]
        for item in (payload.get('type_breakdown') or [])[:15]:
            top_people = ', '.join(
                self._clean_text(person.get('name') or '-')
                for person in (item.get('offenders') or [])[:3]
            ) or '-'
            type_rows.append([
                self._clean_text(item.get('label') or '-'),
                self._clean_text(str(item.get('severity') or '-').upper()),
                self._clean_text(item.get('count', 0)),
                self._clean_text(item.get('offender_count', 0)),
                top_people,
            ])
        story.append(Paragraph("Breakdown per Tipe", self.styles['ViolationsSection']))
        story.append(self._build_table(type_rows, [165, 65, 50, 60, 250], body_font_size=6.8, cell_padding=4))
        story.append(PageBreak())

        story.append(Paragraph("Penjelasan Mudah per Jenis", self.styles['ViolationsSection']))
        story.append(Paragraph(
            "Bagian ini dibuat agar pengawas, wali kelas, dan pihak sekolah yang bukan teknis tetap bisa membaca "
            "arti tiap jenis pelanggaran dengan cepat.",
            self.styles['ViolationsSmall'],
        ))
        story.append(self._build_explanation_cards(payload))
        story.append(Spacer(1, 10))

        detail_rows = [['Waktu', 'Peserta / Kelas', 'Ujian', 'Pelanggaran', 'Ringkasan Konteks']]
        for violation in (payload.get('violations') or [])[:12]:
            detail_rows.append([
                self._clean_text(violation.get('created_at_display') or '-'),
                self._clean_text(
                    f"{violation.get('name') or '-'} / {violation.get('class') or '-'}"
                ),
                self._clean_text(violation.get('exam_title') or '-'),
                self._clean_text(violation.get('label') or violation.get('violation_type') or '-'),
                self._clean_text(violation.get('detail_summary') or '-'),
            ])
        story.append(Paragraph("Log Pelanggaran Terbaru", self.styles['ViolationsSection']))
        story.append(Paragraph(
            "PDF ini menampilkan 12 log terbaru agar laporan tetap ringkas. Gunakan export Excel untuk detail operasional yang lebih panjang.",
            self.styles['ViolationsSmall'],
        ))
        story.append(self._build_table(
            detail_rows,
            [78, 128, 170, 92, 300],
            body_font_size=6.4,
            cell_padding=4,
        ))

        doc.build(story, onFirstPage=self._draw_footer, onLaterPages=self._draw_footer)
        return buffer.getvalue()


class ExamAnalyticsPDF:
    """Generate formal PDF for exam analytics export."""

    SCHOOL_NAME = "MADRASAH ALIYAH NEGERI 1 ROKAN HULU"
    SCHOOL_SUBTITLE = "Laporan Resmi Analitik SIAB1"
    REPORT_BADGE = "Dokumen evaluasi akademik"

    def __init__(self):
        if not REPORTLAB_AVAILABLE:
            raise ImportError("ReportLab not installed. Run: pip install reportlab")
        self.styles = getSampleStyleSheet()
        self.logo_path = self._resolve_logo_path()
        self._create_styles()

    def _resolve_logo_path(self) -> Optional[str]:
        base_dir = Path(__file__).resolve().parents[2]
        candidates = [
            base_dir / "static" / "uploads" / "logo-man1.jpeg",
            base_dir / "tools" / "logoman1.jpeg",
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return None

    def _create_styles(self) -> None:
        self.styles.add(ParagraphStyle(
            name='AnalyticsSchool',
            parent=self.styles['Title'],
            fontSize=17,
            leading=21,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#0f172a'),
            spaceAfter=3,
        ))
        self.styles.add(ParagraphStyle(
            name='AnalyticsSubtitle',
            parent=self.styles['Normal'],
            fontSize=10.5,
            leading=13,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#334155'),
            spaceAfter=2,
        ))
        self.styles.add(ParagraphStyle(
            name='AnalyticsBadge',
            parent=self.styles['Normal'],
            fontSize=9,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#166534'),
            spaceAfter=10,
        ))
        self.styles.add(ParagraphStyle(
            name='AnalyticsSection',
            parent=self.styles['Heading2'],
            fontSize=12,
            leading=14,
            textColor=colors.HexColor('#111827'),
            spaceBefore=10,
            spaceAfter=6,
        ))
        self.styles.add(ParagraphStyle(
            name='AnalyticsMeta',
            parent=self.styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#475569'),
            leading=12,
        ))
        self.styles.add(ParagraphStyle(
            name='AnalyticsSmall',
            parent=self.styles['Normal'],
            fontSize=8,
            textColor=colors.HexColor('#4b5563'),
            leading=10,
        ))

    def _clean_text(self, value: Any) -> str:
        if value is None:
            return ""
        return str(value).encode('latin-1', 'replace').decode('latin-1')

    def _float(self, value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _difficulty_label(self, level: Any) -> str:
        key = str(level or "").lower()
        if key == "easy":
            return "Mudah"
        if key == "medium":
            return "Sedang"
        if key == "hard":
            return "Sulit"
        return "Belum Terklasifikasi"

    def _draw_footer(self, canvas, doc) -> None:
        canvas.saveState()
        width, _ = doc.pagesize
        canvas.setStrokeColor(colors.HexColor('#cbd5e1'))
        canvas.setLineWidth(0.5)
        canvas.line(doc.leftMargin, 0.9 * cm, width - doc.rightMargin, 0.9 * cm)
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.HexColor('#475569'))
        canvas.drawString(doc.leftMargin, 0.52 * cm, self._clean_text(self.SCHOOL_NAME))
        canvas.drawRightString(width - doc.rightMargin, 0.52 * cm, f"Halaman {doc.page}")
        canvas.restoreState()

    def _build_table(
        self,
        rows: List[List[Any]],
        col_widths: List[float],
        *,
        header_bg: str = '#111827',
        header_font_size: int = 8,
        body_font_size: int = 8,
        align_center_cols: Optional[List[int]] = None,
    ) -> Table:
        table = Table(rows, colWidths=col_widths, repeatRows=1)
        style_cmds = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(header_bg)),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, 0), header_font_size),
            ('FONTSIZE', (0, 1), (-1, -1), body_font_size),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#9ca3af')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
        ]
        if align_center_cols:
            for col_idx in align_center_cols:
                style_cmds.append(('ALIGN', (col_idx, 0), (col_idx, -1), 'CENTER'))
        table.setStyle(TableStyle(style_cmds))
        return table

    def generate(self, payload: Dict[str, Any]) -> bytes:
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            rightMargin=1.2 * cm,
            leftMargin=1.2 * cm,
            topMargin=1.1 * cm,
            bottomMargin=1.5 * cm,
        )
        story: List[Any] = []

        exam = payload.get("exam") or {}
        overview = payload.get("overview") or {}
        distribution = payload.get("score_distribution") or overview.get("score_distribution") or {}
        question_analysis = payload.get("question_analysis") or []
        class_performance = payload.get("class_performance")
        class_filter = self._clean_text(payload.get("class_filter") or "Belum dipilih")
        generated_at = self._clean_text(payload.get("generated_at") or datetime.now().strftime("%d-%m-%Y %H:%M"))

        story.append(HRFlowable(width="100%", thickness=1.4, color=colors.HexColor('#166534'), spaceAfter=4))
        if self.logo_path:
            logo = Image(self.logo_path, width=2.6 * cm, height=2.6 * cm)
            logo.hAlign = 'CENTER'
            story.append(logo)
            story.append(Spacer(1, 2))
        story.append(Paragraph(self.SCHOOL_NAME, self.styles['AnalyticsSchool']))
        story.append(Paragraph(self.SCHOOL_SUBTITLE, self.styles['AnalyticsSubtitle']))
        story.append(Paragraph(self.REPORT_BADGE, self.styles['AnalyticsBadge']))

        meta_rows = [
            ['Judul Ujian', f": {self._clean_text(exam.get('title') or '-')}"],
            ['Mata Pelajaran', f": {self._clean_text(exam.get('subject') or '-')}"],
            ['Guru Pelaksana', f": {self._clean_text(exam.get('teacher_name') or '-')}"],
            ['KKM / Passing Score', f": {self._float(exam.get('passing_score') or 70):.2f}"],
            ['Kelas (Tab Performa)', f": {class_filter}"],
            ['Tanggal Export', f": {generated_at}"],
        ]
        meta_table = Table(meta_rows, colWidths=[140, 340], hAlign='LEFT')
        meta_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 2),
            ('RIGHTPADDING', (0, 0), (-1, -1), 2),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 6))

        overview_rows = [
            ['Metrik Overview', 'Nilai'],
            ['Total Peserta', self._clean_text(overview.get('total_participants') or 0)],
            ['Sesi Selesai', self._clean_text(overview.get('completed_sessions') or 0)],
            ['Sesi Aktif', self._clean_text(overview.get('active_sessions') or 0)],
            ['Rata-rata Nilai', f"{self._float(overview.get('average_score')):.2f}"],
            ['Nilai Tertinggi', f"{self._float(overview.get('highest_score')):.2f}"],
            ['Nilai Terendah', f"{self._float(overview.get('lowest_score')):.2f}"],
            ['Tingkat Kelulusan', f"{self._float(overview.get('pass_rate')):.2f}%"],
            ['Total Pelanggaran', self._clean_text((overview.get('violation_stats') or {}).get('total_violations', 0))],
        ]
        story.append(Paragraph("A. Overview", self.styles['AnalyticsSection']))
        story.append(self._build_table(overview_rows, [220, 140], align_center_cols=[1]))
        story.append(Spacer(1, 8))

        completed_sessions = int(overview.get('completed_sessions') or 0)
        distribution_rows = [['Rentang Nilai', 'Jumlah Siswa', 'Persentase']]
        total_distribution = sum(int(v or 0) for v in distribution.values())
        denominator = completed_sessions if completed_sessions > 0 else total_distribution
        for label in ['0-20', '21-40', '41-60', '61-80', '81-100']:
            count = int(distribution.get(label) or 0)
            percentage = (count / denominator * 100) if denominator > 0 else 0
            distribution_rows.append([label, str(count), f"{percentage:.2f}%"])
        story.append(Paragraph("B. Distribusi Nilai", self.styles['AnalyticsSection']))
        story.append(self._build_table(distribution_rows, [180, 120, 120], align_center_cols=[1, 2]))
        story.append(Spacer(1, 8))

        question_rows = [['No', 'Ringkasan Soal', 'Jawaban', 'Benar', '% Benar', 'Kesulitan']]
        if question_analysis:
            for idx, item in enumerate(question_analysis, start=1):
                question_text = self._clean_text(item.get('question_text') or '-')
                if len(question_text) > 170:
                    question_text = f"{question_text[:167]}..."
                question_rows.append([
                    self._clean_text(item.get('question_number') or idx),
                    question_text,
                    self._clean_text(item.get('total_answers') or 0),
                    self._clean_text(item.get('correct_answers') or 0),
                    f"{self._float(item.get('correct_rate')):.2f}%",
                    self._difficulty_label(item.get('difficulty')),
                ])
        else:
            question_rows.append(['-', 'Belum ada data analisis soal', '-', '-', '-', '-'])
        story.append(Paragraph("C. Analisis Soal", self.styles['AnalyticsSection']))
        story.append(self._build_table(
            question_rows,
            [40, 355, 65, 55, 70, 95],
            body_font_size=7,
            align_center_cols=[0, 2, 3, 4],
        ))
        story.append(Spacer(1, 8))

        story.append(Paragraph("D. Performa Siswa (Tab Performa)", self.styles['AnalyticsSection']))
        if class_performance:
            total_students = int(class_performance.get('total_students') or 0)
            if total_students <= 0:
                message = self._clean_text(class_performance.get('message') or 'Belum ada data performa siswa.')
                story.append(Paragraph(message, self.styles['AnalyticsMeta']))
            else:
                class_rows = [
                    ['Metrik Kelas', 'Nilai'],
                    ['Nama Kelas', self._clean_text(class_performance.get('class_name') or '-')],
                    ['Total Siswa', self._clean_text(class_performance.get('total_students') or 0)],
                    ['Total Ujian Diikuti', self._clean_text(class_performance.get('total_exams_taken') or 0)],
                    ['Rata-rata Nilai', f"{self._float(class_performance.get('average_score')):.2f}"],
                    ['Nilai Tertinggi', f"{self._float(class_performance.get('highest_score')):.2f}"],
                    ['Nilai Terendah', f"{self._float(class_performance.get('lowest_score')):.2f}"],
                    ['Tingkat Kelulusan', f"{self._float(class_performance.get('pass_rate')):.2f}%"],
                ]
                story.append(self._build_table(class_rows, [220, 180], align_center_cols=[1]))
                story.append(Spacer(1, 8))

                performers = class_performance.get('top_performers') or []
                performer_rows = [['Peringkat', 'Nama Siswa', 'Rata-rata', 'Total Ujian']]
                if performers:
                    for rank, performer in enumerate(performers[:10], start=1):
                        performer_rows.append([
                            str(rank),
                            self._clean_text(performer.get('name') or '-'),
                            f"{self._float(performer.get('average_score')):.2f}",
                            self._clean_text(performer.get('exams_taken') or 0),
                        ])
                else:
                    performer_rows.append(['-', 'Belum ada data top performers', '-', '-'])
                story.append(Paragraph("Top Performers Kelas", self.styles['AnalyticsMeta']))
                story.append(self._build_table(
                    performer_rows,
                    [70, 320, 90, 90],
                    align_center_cols=[0, 2, 3],
                ))
        else:
            story.append(Paragraph(
                "Data performa siswa belum disertakan karena kelas belum dipilih saat export.",
                self.styles['AnalyticsMeta'],
            ))

        story.append(Spacer(1, 10))
        story.append(Paragraph(
            "Catatan: Laporan ini dibuat otomatis dari data terbaru yang tersedia saat tombol Export dijalankan.",
            self.styles['AnalyticsSmall'],
        ))

        doc.build(story, onFirstPage=self._draw_footer, onLaterPages=self._draw_footer)
        return buffer.getvalue()


def generate_exam_results_pdf(
    exam_title: str,
    exam_date: str,
    results: List[Dict],
    summary: Dict,
    creator_name: Optional[str] = None
) -> bytes:
    """Helper function to generate exam results PDF."""
    generator = ExamResultPDF()
    return generator.generate(exam_title, exam_date, results, summary, creator_name)


def generate_certificate_pdf(
    student_name: str,
    exam_title: str,
    score: float,
    completion_date: str,
    certificate_id: str
) -> bytes:
    """Helper function to generate certificate PDF."""
    generator = CertificatePDF()
    return generator.generate(
        student_name, exam_title, score,
        completion_date, certificate_id
    )


def generate_violations_report_pdf(payload: Dict[str, Any]) -> bytes:
    """Helper function to generate violations dashboard PDF export."""
    generator = ViolationsReportPDF()
    return generator.generate(payload)


def generate_exam_analytics_pdf(payload: Dict[str, Any]) -> bytes:
    """Helper function to generate exam analytics PDF export."""
    generator = ExamAnalyticsPDF()
    return generator.generate(payload)

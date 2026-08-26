"""Small dependency-free PDF renderer for record exports."""

from __future__ import annotations

from collections.abc import Iterable

from biodata.schemas import BioRecordRead


def _pdf_text(value: str) -> str:
    escaped = value.encode("latin-1", "replace").decode("latin-1")
    return escaped.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _page_content(records: list[BioRecordRead], page_number: int, page_count: int) -> bytes:
    lines = [
        "Biodata records",
        f"Page {page_number} of {page_count}",
        "",
        "Name | Email | Phone | Age | BMI | Date of birth",
    ]
    lines.extend(
        f"{record.full_name} | {record.email} | {record.phone or '-'} | "
        f"{record.age} | {record.bmi:.1f} | {record.date_of_birth.isoformat()}"
        for record in records
    )

    commands = ["BT", "/F1 9 Tf", "40 800 Td"]
    for index, line in enumerate(lines):
        if index:
            commands.append("0 -16 Td")
        commands.append(f"({_pdf_text(line)}) Tj")
    commands.append("ET")
    return "\n".join(commands).encode("latin-1")


def render_records(records: Iterable[BioRecordRead]) -> bytes:
    """Render records as a paginated, downloadable PDF document."""
    record_list = list(records)
    pages = [record_list[index : index + 42] for index in range(0, len(record_list), 42)] or [[]]
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    page_numbers: list[int] = []
    for page_number, page_records in enumerate(pages, start=1):
        content = _page_content(page_records, page_number, len(pages))
        content_number = len(objects) + 2
        page_number_object = len(objects) + 1
        objects.extend(
            [
                (
                    f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] "
                    f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_number} 0 R >>"
                ).encode("ascii"),
                f"<< /Length {len(content)} >>\nstream\n".encode("ascii") + content + b"\nendstream",
            ]
        )
        page_numbers.append(page_number_object)
    objects[1] = (
        f"<< /Type /Pages /Kids [{ ' '.join(f'{number} 0 R' for number in page_numbers) }] "
        f"/Count {len(page_numbers)} >>"
    ).encode("ascii")

    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode("ascii"))
        output.extend(body)
        output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode(
            "ascii"
        )
    )
    return bytes(output)
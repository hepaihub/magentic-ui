from hepai import HRModel
import base64, os





def pdf_parser_by_mineru(pdf_path):

    model = HRModel.connect(
        name="hepai/mineru_pdf",
        base_url="http://localhost:4261/apiv2"
    )

    with open(pdf_path, "rb") as f:
        pdf_base64 = base64.b64encode(f.read()).decode('utf-8')
        result = model.interface(
            pdf_base64=pdf_base64
            )
        return result

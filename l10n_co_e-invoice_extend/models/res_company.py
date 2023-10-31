from odoo import _, api, fields, models, tools
import logging
_logger = logging.getLogger(__name__)

try:
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    import OpenSSL
    from OpenSSL import crypto

    type_ = crypto.FILETYPE_PEM
except ImportError:
    _logger.warning("Cannot import OpenSSL library")

from cryptography.x509 import oid
from cryptography.hazmat.primitives import serialization

import base64

from io import BytesIO

class ResCompany(models.Model):
    _inherit = "res.company"

    issuer_name = fields.Char(required=False, default='/')
    serial_number = fields.Char(required=False, default='/')
    certificate_key = fields.Char(required=False, default='/')

    def button_extract_certificate(self):
        password = self.certificate_key
        archivo_key = base64.b64decode(self.certificate_file)
        p12 = crypto.load_pkcs12(archivo_key, password)
        x509 = p12.get_certificate().to_cryptography()

        def get_reversed_rdns_name(rdns):
            """
            Gets the rdns String name, but in the right order. xmlsig original function produces a reversed order
            :param rdns: RDNS object
            :type rdns: cryptography.x509.RelativeDistinguishedName
            :return: RDNS name
            """
            OID_NAMES = {
                oid.NameOID.COMMON_NAME: 'CN',
                oid.NameOID.COUNTRY_NAME: 'C',
                oid.NameOID.DOMAIN_COMPONENT: 'DC',
                oid.NameOID.EMAIL_ADDRESS: 'E',
                oid.NameOID.GIVEN_NAME: 'G',
                oid.NameOID.LOCALITY_NAME: 'L',
                oid.NameOID.ORGANIZATION_NAME: 'O',
                oid.NameOID.ORGANIZATIONAL_UNIT_NAME: 'OU',
                oid.NameOID.SURNAME: 'SN'
            }
            name = ''
            for rdn in reversed(rdns):
                for attr in rdn._attributes:
                    if len(name) > 0:
                        name = name + ','
                    if attr.oid in OID_NAMES:
                        name = name + OID_NAMES[attr.oid]
                    else:
                        name = name + attr.oid._name
                    name = name + '=' + attr.value
            return name
        isuuer = get_reversed_rdns_name(x509.issuer.rdns)

        s = base64.b64encode(
            x509.public_bytes(encoding=serialization.Encoding.DER)
        )
        self.issuer_name = isuuer
        self.serial_number = x509.serial_number
        self.digital_certificate = str(s, 'utf8')
        output = BytesIO()
        output.write(crypto.dump_certificate(crypto.FILETYPE_PEM, p12.get_certificate()))
        output.seek(0)
        self.pem = "Certificate.pem"
        self.pem_file = base64.b64encode(output.read())

        archivo_pem = base64.b64decode(self.pem_file)
        pem = crypto.load_certificate(crypto.FILETYPE_PEM, archivo_pem)
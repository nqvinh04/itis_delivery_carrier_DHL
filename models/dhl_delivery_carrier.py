import binascii
import logging
import requests
from datetime import datetime
import xml.etree.ElementTree as etree
from xml.etree import ElementTree
from xml.etree.ElementTree import Element
from xml.etree.ElementTree import SubElement
from urllib.parse import quote_plus
from odoo import api, fields, models
from odoo.exceptions import ValidationError

# https://github.com/alfallouji/DHL-API
_logger = logging.getLogger(__name__)
try:
    from urllib3.exceptions import HTTPError
    import urllib3
except Exception as e:
    _logger.error("#ITISDEBUG-1  python  urllib3 library not installed .")


class DHLApiConfig:
    ApiEnd = {
        'test': 'https://xmlpitest-ea.dhl.com/XMLShippingServlet',
        'production': 'https://xmlpi-ea.dhl.com/XMLShippingServlet',
        'tracking': "http://www.dhl.com/en/express/tracking.html"
    }

    ApiReturn = {
        'test': 'https://xmlpitest-ea.dhl.com/services/sandbox/rest/returns',
        'production': 'https://xmlpi-ea.dhl.com/services/sandbox/rest/returns',
    }

    @staticmethod
    def check_error(root):
        error = False
        ConditionData = root.getiterator("ConditionData")
        for ConditionCode in root.getiterator("ConditionCode"):
            if ConditionCode.text not in ['DIV001', 'SV009']:
                error = True
        if error:
            return ','.join([i.text for i in ConditionData])

    @classmethod
    def get_tracking(cls, awb):
        return '%s?AWB=%s' % (cls.ApiEnd.get('tracking'), quote_plus(awb))

    @staticmethod
    def current_message_time():
        return datetime.now().strftime("%Y-%m-%dT%H:%M:%S GMT")

    @staticmethod
    def add_elem_text(elem, text):
        elem.text = text
        return elem

    @staticmethod
    def rough_string(elem):
        rough_string = ElementTree.tostring(elem, 'utf-8')
        return rough_string.decode('utf-8')

    def __init__(self, *args, **kwargs):
        self.dhl_site_id = kwargs.get('dhl_site_id')
        self.dhl_password = kwargs.get('dhl_password')
        self.dhl_account_no = kwargs.get('dhl_account_no')
        self.dhl_currency = kwargs.get('dhl_currency')
        self.dhl_environment = kwargs.get('dhl_environment', 'test')
        self.dhl_label_format = kwargs.get('dhl_label_format')
        self.dhl_label_type = kwargs.get('dhl_label_type')

    def send_request(self, request_xml, request_type):
        try:
            api_end = self.ApiEnd.get(self.dhl_environment or 'test')
            api_return = self.ApiReturn.get(self.dhl_environment or 'test')
            _logger.info("DHL api_end=%r==" % api_end)
            if request_type == 'ship':
                response = requests.request('POST', api_end, data=request_xml.encode('utf-8'))
            if request_type == 'return':
                response = requests.request('POST', api_return, data=request_xml.encode('utf-8'))
            root = etree.fromstring(response.text)
            error = self.check_error(root)
            return dict(success=0 if error else 1, error_message=error, root=root)
        except Exception as err:
            _logger.warning(
                "#Itis---DHL %r Exception-----%r---------" % (request_xml, err))
            return dict(success=False, error_message=err)

    def send_request_rate(self, data, request_type):
        response = self.send_request(data, request_type)
        if response.get('error_message'):
            return response
        root = response.get('root')
        price = 0
        currency = None
        ShippingCharge = list(root.iterfind('GetQuoteResponse/BkgDetails/QtdShp/ShippingCharge'))
        CurrencyCode = list(root.iterfind('GetQuoteResponse/BkgDetails/QtdShp/CurrencyCode'))
        if len(ShippingCharge):
            price = float(ShippingCharge[0].text)
        if len(CurrencyCode):
            currency = CurrencyCode[0].text
        return dict(price=price, currency=currency, success=True)

    def _process_shipment(self, data, request_type):
        response = self.send_request(data, request_type)
        if response.get('error_message'):
            return response
        root = response.get('root')
        currency = 'USD'
        amount = root.findtext('ShippingCharge')
        tracking_result = {}
        for tracking_number, docformat, image in zip(root.getiterator("AirwayBillNumber"),
                                                     root.getiterator("OutputFormat"),
                                                     root.getiterator("OutputImage")):
            if docformat.text == "pdf":
                tracking_result[tracking_number.text] = (
                    'DHL' + str(tracking_number.text) + '.pdf', binascii.a2b_base64(image.text))
            elif docformat.text == "zpl2":
                tracking_result[tracking_number.text] = (
                    'DHL' + str(tracking_number.text) + '.zpl', binascii.a2b_base64(image.text))
            elif docformat.text == "epl2":
                tracking_result[tracking_number.text] = (
                    'DHL' + str(tracking_number.text) + '.epl', binascii.a2b_base64(image.text))
        return dict(currency=currency, amount=amount, tracking_result=tracking_result)

    def construct_request(self):
        request = Element("Request")
        serviceHeader = SubElement(request, 'ServiceHeader')
        self.add_elem_text(SubElement(serviceHeader, 'MessageTime'), self.current_message_time())
        self.add_elem_text(SubElement(serviceHeader, 'MessageReference'), '1234567890123456789012345678901')
        self.add_elem_text(SubElement(serviceHeader, 'SiteID'), self.dhl_site_id)
        self.add_elem_text(SubElement(serviceHeader, 'Password'), self.dhl_password)
        metaData = SubElement(request, 'MetaData')
        self.add_elem_text(SubElement(metaData, 'SoftwareName'), 'Odoo')
        self.add_elem_text(SubElement(metaData, 'SoftwareVersion'), '12.0')
        return request

    def construct_piece(self, data, pickings=False):
        piece = Element("Piece")
        if data.get('piece_id'):
            self.add_elem_text(SubElement(piece, 'PieceID'), '%s' % data.get('piece_id'))

        if not pickings:
            self.add_elem_text(SubElement(piece, 'Height'), '%s' % int(round(data.get('height'))))
            self.add_elem_text(SubElement(piece, 'Depth'), '%s' % int(round(data.get('depth'))))
            self.add_elem_text(SubElement(piece, 'Width'), '%s' % int(round(data.get('width'))))
            self.add_elem_text(SubElement(piece, 'Weight'), '%s' % data.get('weight'))
        else:
            if data.get('shipper_package_code'):
                self.add_elem_text(SubElement(piece, 'PackageType'), data.get('shipper_package_code'))
            self.add_elem_text(SubElement(piece, 'Weight'), '%s' % data.get('weight'))
            self.add_elem_text(SubElement(piece, 'Width'), '%s' % int(round(data.get('width'))))
            self.add_elem_text(SubElement(piece, 'Height'), '%s' % int(round(data.get('height'))))
            self.add_elem_text(SubElement(piece, 'Depth'), '%s' % int(round(data.get('depth'))))
        return piece

    def construct_dutiable(self, data, picking=False):
        dutiable = Element('Dutiable')
        if not picking:
            self.add_elem_text(SubElement(dutiable, 'DeclaredCurrency'), self.dhl_currency)
            self.add_elem_text(SubElement(dutiable, 'DeclaredValue'), '%.2f' % float(data.get('declared_value')))
        else:
            self.add_elem_text(SubElement(dutiable, 'DeclaredValue'), '%.2f' % data.get('declared_value'))
            self.add_elem_text(SubElement(dutiable, 'DeclaredCurrency'), self.dhl_currency)
            if data.get('term_of_trade'):
                self.add_elem_text(SubElement(dutiable, 'TermsOfTrade'), data.get('term_of_trade'))
        return dutiable

    def construct_export_declaration(self, data, pickings=None):
        addDecText1 = data.get("declaration_text1")
        addDecText2 = data.get("declaration_text2")
        addDecText3 = data.get("declaration_text3")
        exportDeclaration = Element('ExportDeclaration')
        self.add_elem_text(SubElement(exportDeclaration, 'InvoiceNumber'),
                           'INV-OF-{}'.format(pickings.origin or pickings.name))
        self.add_elem_text(SubElement(exportDeclaration, 'InvoiceDate'),
                           fields.Datetime.from_string(pickings.scheduled_date).strftime("%Y-%m-%d"))
        if data.get('exporter_code'):
            self.add_elem_text(SubElement(exportDeclaration, 'ExporterCode'), data.get('exporter_code'))
        self.add_elem_text(SubElement(exportDeclaration, 'AddDecText1'), addDecText1)
        self.add_elem_text(SubElement(exportDeclaration, 'AddDecText2'), addDecText2)
        self.add_elem_text(SubElement(exportDeclaration, 'AddDecText3'), addDecText3)

        for package_id, move_id in zip(pickings.package_ids, pickings.move_ids_without_package):
            index = 1
            pkg_data = package_id.read(['weight', 'height', 'width', 'length', 'cover_amount'])[0]
            exportLineItem = Element('ExportLineItem')
            self.add_elem_text(SubElement(exportLineItem, 'LineNumber'), str(index))
            self.add_elem_text(SubElement(exportLineItem, 'Quantity'), '1')
            self.add_elem_text(SubElement(exportLineItem, 'QuantityUnit'), 'BOX')
            self.add_elem_text(SubElement(exportLineItem, 'Description'), 'Package')
            self.add_elem_text(SubElement(exportLineItem, 'Value'), str(pkg_data.get('cover_amount')))
            self.add_elem_text(SubElement(exportLineItem, 'CommodityCode'), str(move_id.product_id.hs_code))
            Weight = Element('Weight')
            self.add_elem_text(SubElement(Weight, 'Weight'), str(round(float(pkg_data.get('weight')), 2)))
            self.add_elem_text(SubElement(Weight, 'WeightUnit'), data.get('weight_unit'))
            exportLineItem.append(Weight)
            grossWeight = Element('GrossWeight')
            self.add_elem_text(SubElement(grossWeight, 'Weight'), str(pickings.shipping_weight))
            self.add_elem_text(SubElement(grossWeight, 'WeightUnit'), data.get('weight_unit'))
            exportLineItem.append(grossWeight)
            exportLineItem.append(exportLineItem)
            index += 1
        return exportDeclaration

    def construct_quote_address(self, addr_type, data):
        address = Element(addr_type)
        self.add_elem_text(SubElement(address, 'CountryCode'), data.get('country_code'))
        self.add_elem_text(SubElement(address, 'Postalcode'), data.get('zip'))
        self.add_elem_text(SubElement(address, 'City'), data.get('city'))
        return address

    def construct_bkg_details(self, data, shipper_data, pieces):
        bkgDetails = Element('BkgDetails')
        self.add_elem_text(SubElement(bkgDetails, 'PaymentCountryCode'), shipper_data.get('country_code'))
        self.add_elem_text(SubElement(bkgDetails, 'Date'), data.get('ship_date'))
        self.add_elem_text(SubElement(bkgDetails, 'ReadyTime'), data.get('ready_time'))

        self.add_elem_text(SubElement(bkgDetails, 'DimensionUnit'), data.get('dimension_unit'))
        self.add_elem_text(SubElement(bkgDetails, 'WeightUnit'), data.get('weight_unit'))
        bkgDetails.append(pieces)
        self.add_elem_text(SubElement(bkgDetails, 'PaymentAccountNumber'), self.dhl_account_no)
        self.add_elem_text(SubElement(bkgDetails, 'IsDutiable'), data.get('is_dutiable'))
        self.add_elem_text(SubElement(bkgDetails, 'NetworkTypeCode'), 'AL')

        qtdShp = SubElement(bkgDetails, 'QtdShp')
        self.add_elem_text(SubElement(qtdShp, 'GlobalProductCode'), data.get('global_code'))
        self.add_elem_text(SubElement(qtdShp, 'LocalProductCode'), data.get('local_code'))
        if data.get('term_of_trade') == 'DDP':
            qtdShpExChrg = SubElement(qtdShp, 'QtdShpExChrg')
            self.add_elem_text(SubElement(qtdShpExChrg, 'SpecialServiceType'), 'DD')
        if data.get('is_insured') == 'yes':
            qtdShpExChrg = SubElement(qtdShp, 'QtdShpExChrg')
            self.add_elem_text(SubElement(qtdShpExChrg, 'SpecialServiceType'), 'II')
        return bkgDetails

    def construct_rate_request_dhl(self, data, shipper_data, recipient_data, pieces):
        attrib = {
            "xmlns:p": "http://www.dhl.com",
            "xmlns:p1": "http://www.dhl.com/datatypes",
            "xmlns:p2": "http://www.dhl.com/DCTRequestdatatypes",
            "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "xsi:schemaLocation": "http://www.dhl.com DCT-req.xsd",
            "schemaVersion": "2.0",
        }
        dCTRequest = Element('p:DCTRequest', attrib=attrib)
        getQuote = SubElement(dCTRequest, 'GetQuote')
        getQuote.append(self.construct_request())
        getQuote.append(self.construct_quote_address('From', shipper_data))
        getQuote.append(self.construct_bkg_details(data, shipper_data, pieces))
        getQuote.append(self.construct_quote_address('To', recipient_data))
        if data.get('is_dutiable') != 'no':
            getQuote.append(self.construct_dutiable(data))
        return dCTRequest

    def construct_ship_address(self, addr_type, data):
        """addr_type==>Consignee,Shipper"""
        addressRoot = Element(addr_type)
        if addr_type == 'Shipper':
            self.add_elem_text(SubElement(addressRoot, 'ShipperID'), self.dhl_account_no)
        self.add_elem_text(SubElement(addressRoot, 'CompanyName'), data.get('company_name') or data.get('name'))
        self.add_elem_text(SubElement(addressRoot, 'AddressLine'), data.get('street'))
        self.add_elem_text(SubElement(addressRoot, 'AddressLine'), data.get('street2'))
        self.add_elem_text(SubElement(addressRoot, 'City'), data.get('city'))
        self.add_elem_text(SubElement(addressRoot, 'PostalCode'), data.get('zip'))
        self.add_elem_text(SubElement(addressRoot, 'CountryCode'), data.get('country_code'))
        self.add_elem_text(SubElement(addressRoot, 'CountryName'), data.get('country_name'))
        contact = SubElement(addressRoot, 'Contact')
        self.add_elem_text(SubElement(contact, 'PersonName'), data.get('name'))
        self.add_elem_text(SubElement(contact, 'PhoneNumber'), data.get('phone'))
        return addressRoot

    def construct_shipment_details(self, data, pieces):
        shipmentDetails = Element('ShipmentDetails')
        self.add_elem_text(SubElement(shipmentDetails, 'NumberOfPieces'), '%s' % data.get('number_of_pieces'))
        shipmentDetails.append(pieces)
        self.add_elem_text(SubElement(shipmentDetails, 'Weight'), '%s' % data.get('weight'))
        self.add_elem_text(SubElement(shipmentDetails, 'WeightUnit'), data.get('weight_unit'))
        self.add_elem_text(SubElement(shipmentDetails, 'GlobalProductCode'), data.get('global_code'))
        self.add_elem_text(SubElement(shipmentDetails, 'LocalProductCode'), data.get('local_code'))
        self.add_elem_text(SubElement(shipmentDetails, 'Date'), data.get('ship_date'))
        self.add_elem_text(SubElement(shipmentDetails, 'Contents'), data.get('contents'))
        self.add_elem_text(SubElement(shipmentDetails, 'DoorTo'), data.get('drop_off_type'))
        self.add_elem_text(SubElement(shipmentDetails, 'DimensionUnit'), data.get('dimension_unit'))

        if data.get('is_insured') == 'yes':
            self.add_elem_text(SubElement(shipmentDetails, 'InsuredAmount'), '%.2f' % data.get('declared_value'))
        self.add_elem_text(SubElement(shipmentDetails, 'PackageType'), data.get('shipper_package_code'))
        self.add_elem_text(SubElement(shipmentDetails, 'IsDutiable'), data.get('is_dutiable'))
        self.add_elem_text(SubElement(shipmentDetails, 'CurrencyCode'), self.dhl_currency)

        return shipmentDetails

    def construct_ship_request_dhl(self, data, shipper_data, recipient_data, pieces, pickings=None):
        attrib = {
            "xmlns:req": "http://www.dhl.com",
            "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "xsi:schemaLocation": "http://www.dhl.com ship-val-global-req.xsd",
            "schemaVersion": "6.2"
        }

        requestEA = Element('req:ShipmentRequest', attrib=attrib)
        requestEA.append(self.construct_request())
        self.add_elem_text(SubElement(requestEA, 'LanguageCode'), shipper_data.get('lang')[:2])
        self.add_elem_text(SubElement(requestEA, 'PiecesEnabled'), 'Y')

        billing = Element('Billing')
        self.add_elem_text(SubElement(billing, 'ShipperAccountNumber'), self.dhl_account_no)
        self.add_elem_text(SubElement(billing, 'ShippingPaymentType'), 'S')
        if data.get('term_of_trade') == 'DDP':
            self.add_elem_text(SubElement(billing, 'DutyPaymentType'), 'S')
            self.add_elem_text(SubElement(billing, 'DutyAccountNumber'), self.dhl_account_no)
        requestEA.append(billing)

        requestEA.append(self.construct_ship_address('Consignee', recipient_data))
        if data.get('is_dutiable') != 'no':
            requestEA.append(self.construct_dutiable(data, True))

        self.add_elem_text(SubElement(requestEA, 'UseDHLInvoice'), 'Y')
        self.add_elem_text(SubElement(requestEA, 'DHLInvoiceLanguageCode'), 'en')
        self.add_elem_text(SubElement(requestEA, 'DHLInvoiceType'), 'CMI')
        requestEA.append(self.construct_export_declaration(data, pickings=pickings))
        reference = Element('Reference')
        self.add_elem_text(SubElement(reference, 'ReferenceID'), data.get('reference'))
        requestEA.append(reference)
        requestEA.append(self.construct_shipment_details(data, pieces))
        requestEA.append(self.construct_ship_address('Shipper', shipper_data))
        if data.get('term_of_trade') == 'DDP':
            specialService = SubElement(requestEA, 'SpecialService')
            self.add_elem_text(SubElement(specialService, 'SpecialServiceType'), 'DD')
        if data.get('is_insured') == 'yes':
            specialService = SubElement(requestEA, 'SpecialService')
            self.add_elem_text(SubElement(specialService, 'SpecialServiceType'), 'II')
            self.add_elem_text(SubElement(specialService, 'ChargeValue'), '%.2f' % data.get('declared_value'))
            self.add_elem_text(SubElement(specialService, 'CurrencyCode'), self.dhl_currency)
        self.add_elem_text(SubElement(requestEA, 'LabelImageFormat'), self.dhl_label_format)
        label = SubElement(requestEA, 'Label')
        self.add_elem_text(SubElement(label, 'LabelTemplate'), self.dhl_label_type)
        return requestEA


class DeliveryCarrier(models.Model):
    _inherit = "delivery.carrier"

    def _compute_can_generate_return(self):
        super()._compute_can_generate_return()
        for carrier in self:
            if carrier.delivery_type == 'dhl':
                carrier.can_generate_return = True

    @api.model
    def dhl_get_shipping_price_piece(self, sdk, order):
        pass

    @api.model
    def dhl_get_shipping_data(self, order=None, pickings=None):
        res = self.dhl_service_id.read(['is_dutiable', 'is_insured', 'global_code', 'local_code', 'term_of_trade'])[0]
        res.pop('id')
        if order:
            result = {
                'ship_date': fields.Datetime.from_string(order.date_order).strftime("%Y-%m-%d"),
                'dimension_unit': (self.delivery_uom == 'KG') and 'CM' or 'IN',
                'weight_unit': (self.delivery_uom == 'KG') and 'KG' or 'LB',
                'reference': order.name or order.origin,
            }
            res.update(result)
        else:
            contents = 'Customer Order %s' % pickings.name
            if pickings.origin:
                contents = 'Customer Order Reference ' + pickings.origin

            result = {
                'ship_date': fields.Datetime.from_string(pickings.scheduled_date).strftime("%Y-%m-%d"),
                'dimension_unit': (self.delivery_uom == 'KG') and 'C' or 'I',
                'weight_unit': (self.delivery_uom == 'KG') and 'K' or 'L',
                'reference': pickings.origin or pickings.name,
                'drop_off_type': self.dhl_drop_off_id.code,
                'contents': contents,
            }
            res.update(result)

        return res

    @api.model
    def dhl_get_shipping_price(self, order):
        packaging = self.env['product.packaging']
        currency_id = self.get_shipment_currency_id(order)
        currency_code = currency_id.name
        shipper_info = self.get_shipment_shipper_address(order)
        recipient_info = self.get_shipment_recipient_address(order)
        data = self.dhl_get_shipping_data(order)
        config = self.wk_get_carrier_settings(['dhl_site_id', 'dhl_account_no', 'dhl_password', 'prod_environment'])
        config['dhl_environment'] = 'production' if config['prod_environment'] else 'test'
        config['dhl_currency'] = currency_code
        sdk = DHLApiConfig(**config)

        package_items = self.wk_get_order_package(order=order)
        items = self.wk_group_by('packaging_id', package_items)
        result = {}
        tot_price = 0
        index = 1
        for order_packaging_id, wk_package_ids in items:
            packaging_id = packaging.browse(order_packaging_id)
            wk_cover_amount = sum(map(lambda i: i.get('wk_cover_amount', 0), wk_package_ids))
            declared_value = packaging_id.get_cover_amount(wk_cover_amount) or 0
            pieces = Element('Pieces')
            for package_id in wk_package_ids:
                weight = round(self._get_api_weight(package_id.get('weight')), 3)
                weight = weight and weight or self.default_product_weight
                piece_data = {
                    'piece_id': index,
                    'height': package_id.get('height'),
                    'depth': package_id.get('width'),
                    'width': package_id.get('length'),
                    'weight': weight,
                }
                pieces.append(sdk.construct_piece(piece_data))
                index += 1
            data['ready_time'] = 'PT%sH00M' % (packaging_id.ready_time_dhl)
            data['declared_value'] = str(round(declared_value, 2))

            rate_req = sdk.construct_rate_request_dhl(
                data, shipper_info, recipient_info, pieces)
            rate_req_xml = sdk.rough_string(rate_req)
            response = sdk.send_request_rate(rate_req_xml, request_type='ship')
            if response.get('error_message'):
                return response
            else:
                tot_price += response.get('price')
                result['currency'] = response.get('price')
        result['success'] = True
        result['price'] = tot_price
        result['currency_id'] = currency_id
        return result

    @api.model
    def dhl_rate_shipment(self, order):
        response = self.dhl_get_shipping_price(order)
        if not response.get('error_message'):
            response['error_message'] = None
        if not response.get('price'):
            response['price'] = 0
        if not response.get('warning_message'):
            response['warning_message'] = None
        if not response.get('success'):
            return response
        price = self.convert_shipment_price(response)
        response['price'] = price

        return response

    def dhl_send_shipping(self, pickings):
        for obj in self:
            result = {
                'exact_price': 0,
                'weight': 0,
                'date_delivery': None,
                'tracking_number': '',
                'attachments': []
            }
            currency_id = obj.get_shipment_currency_id(pickings=pickings)
            currency_code = currency_id.name
            total_package = 0
            shipper_info = obj.get_shipment_shipper_address(picking=pickings)
            recipient_info = obj.get_shipment_recipient_address(picking=pickings)

            config = obj.wk_get_carrier_settings(
                ['dhl_site_id', 'dhl_account_no', 'dhl_password', 'prod_environment', 'dhl_label_format',
                 'dhl_label_type', 'exporter_code', 'declaration_text1', 'declaration_text2', 'declaration_text3'])
            config['dhl_environment'] = 'production' if config['prod_environment'] else 'test'
            config['dhl_currency'] = currency_code
            sdk = DHLApiConfig(**config)
            packaging_ids = obj.wk_group_by_packaging(pickings=pickings)
            for packaging_id, package_ids in packaging_ids.items():
                declared_value = sum(map(lambda i: i.cover_amount, package_ids))
                weight_value = 0
                index = 1
                pkg_data = packaging_id.read(['height', 'width', 'packaging_length', 'shipper_package_code'])[0]
                number_of_packages = len(package_ids)
                total_package += number_of_packages
                pieces = Element('Pieces')
                for package_id in package_ids:
                    weight = obj._get_api_weight(package_id.shipping_weight)
                    weight = weight and weight or obj.default_product_weight

                    weight_value += weight
                    piece_data = {
                        'piece_id': index,
                        'weight': weight,
                        'height': pkg_data.get('height'),
                        'depth': pkg_data.get('width'),
                        'width': pkg_data.get('packaging_length'),
                        'shipper_package_code': pkg_data.get('shipper_package_code')
                    }
                    pieces.append(sdk.construct_piece(piece_data, pickings=pickings))
                    index += 1

                data = obj.dhl_get_shipping_data(pickings=pickings)
                data['weight'] = weight_value
                data['declared_value'] = declared_value
                data['number_of_pieces'] = index - 1
                data['shipper_package_code'] = pkg_data.get('shipper_package_code')
                data['exporter_code'] = config.get('exporter_code')
                data['declaration_text1'] = config.get('declaration_text1')
                data['declaration_text2'] = config.get('declaration_text2')
                data['declaration_text3'] = config.get('declaration_text3')
                ship_req = sdk.construct_ship_request_dhl(
                    data, shipper_info, recipient_info, pieces, pickings=pickings)
                ship_req_xml = sdk.rough_string(ship_req)
                dhl_response = sdk._process_shipment(ship_req_xml, request_type='ship')
                if dhl_response.get('error_message'):
                    raise ValidationError(dhl_response.get('error_message'))
                tracking_result = dhl_response.get('tracking_result')
                result['weight'] += weight_value
                if tracking_result:
                    result['tracking_number'] += ','.join(tracking_result.keys())
                    result['attachments'] += list(tracking_result.values())
            return result

    @api.model
    def dhl_cancel_shipment(self, picking):
        return DHLApiConfig.get_tracking(picking.carrier_tracking_ref)

    @api.model
    def dhl_cancel_shipment(self, pickings):
        raise ValidationError('DHL not allow this cancellation of Shipment.')

    @api.model
    def dhl_get_return_label(self, pickings, tracking_number, origin_date):
        # raise ValidationError("DHL Do Not Provide Return Label")
        for obj in self:
            result = {
                'exact_price': 0,
                'weight': 0,
                'date_delivery': None,
                'tracking_number': '',
                'attachments': []
            }
            currency_id = obj.get_shipment_currency_id(pickings=pickings)
            currency_code = currency_id.name
            total_package = 0
            shipper_info = obj.get_shipment_shipper_address(picking=pickings)
            recipient_info = obj.get_shipment_recipient_address(picking=pickings)

            config = obj.wk_get_carrier_settings(
                ['dhl_site_id', 'dhl_account_no', 'dhl_password', 'prod_environment', 'dhl_label_format',
                 'dhl_label_type', 'exporter_code', 'declaration_text1', 'declaration_text2', 'declaration_text3'])
            config['dhl_environment'] = 'production' if config['prod_environment'] else 'test'
            config['dhl_currency'] = currency_code
            sdk = DHLApiConfig(**config)
            packaging_ids = obj.wk_group_by_packaging(pickings=pickings)
            for packaging_id, package_ids in packaging_ids.items():
                declared_value = sum(map(lambda i: i.cover_amount, package_ids))
                weight_value = 0
                index = 1
                pkg_data = packaging_id.read(['height', 'width', 'packaging_length', 'shipper_package_code'])[0]
                number_of_packages = len(package_ids)
                total_package += number_of_packages
                pieces = Element('Pieces')
                for package_id in package_ids:
                    weight = obj._get_api_weight(package_id.shipping_weight)
                    weight = weight and weight or obj.default_product_weight

                    weight_value += weight
                    piece_data = {
                        'piece_id': index,
                        'weight': weight,
                        'height': pkg_data.get('height'),
                        'depth': pkg_data.get('width'),
                        'width': pkg_data.get('packaging_length'),
                        'shipper_package_code': pkg_data.get('shipper_package_code')
                    }
                    pieces.append(sdk.construct_piece(piece_data, pickings=pickings))
                    index += 1

                data = obj.dhl_get_shipping_data(pickings=pickings)
                data['weight'] = weight_value
                data['declared_value'] = declared_value
                data['number_of_pieces'] = index - 1
                data['shipper_package_code'] = pkg_data.get('shipper_package_code')
                data['exporter_code'] = config.get('exporter_code')
                data['declaration_text1'] = config.get('declaration_text1')
                data['declaration_text2'] = config.get('declaration_text2')
                data['declaration_text3'] = config.get('declaration_text3')
                ship_req = sdk.construct_ship_request_dhl(
                    data, shipper_info, recipient_info, pieces, pickings=pickings)
                ship_req_xml = sdk.rough_string(ship_req)
                response_return = sdk._process_shipment(ship_req_xml, request_type='return')
                if response_return.get('error_message'):
                    raise ValidationError(response_return.get('error_message'))
                tracking_result = response_return.get('tracking_result')
                result['weight'] += weight_value
                if tracking_result:
                    result['tracking_number'] += ','.join(tracking_result.keys())
                    result['attachments'] += list(tracking_result.values())
            return result

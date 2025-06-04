import json
import io
from datetime import datetime
from typing import Union
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

class PDFService:
    @staticmethod
    def safe_strftime(date_value: Union[str, datetime], format_string: str) -> str:
        """Safely format date whether it's a string or datetime object"""
        if isinstance(date_value, str):
            # Parse ISO format string back to datetime
            try:
                if 'T' in date_value:
                    # Handle ISO format with time
                    date_value = datetime.fromisoformat(date_value.replace('Z', '+00:00'))
                else:
                    # Handle date-only format
                    date_value = datetime.fromisoformat(date_value)
            except ValueError as e:
                # If parsing fails, return the original string
                return date_value
        
        return date_value.strftime(format_string)
    
    @staticmethod
    def generate_trip_invoice(trip: 'TripResponse', user: 'UserResponse') -> bytes:
        """Generate PDF invoice for a trip"""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        story = []
        
        # Get styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            alignment=TA_CENTER,
            spaceAfter=30,
            textColor=colors.darkblue
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=14,
            alignment=TA_LEFT,
            spaceBefore=20,
            spaceAfter=10,
            textColor=colors.darkblue
        )
        
        # Title
        story.append(Paragraph("TRAVEL INVOICE", title_style))
        story.append(Spacer(1, 20))
        
        # Invoice header info
        header_data = [
            ["Invoice Number:", trip.trip_code, "Date:", datetime.now().strftime("%Y-%m-%d")],
            ["Customer:", f"{user.first_name} {user.last_name}" if user.first_name else user.email, "Status:", trip.status.title()],
            ["Email:", user.email, "Trip Type:", trip.trip_type.title()],
        ]
        
        header_table = Table(header_data, colWidths=[1.5*inch, 2.5*inch, 1*inch, 2*inch])
        header_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (3, 0), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(header_table)
        story.append(Spacer(1, 30))
        
        # Trip Details
        story.append(Paragraph("Trip Details", heading_style))
        
        trip_data = [
            ["Trip Title:", trip.title],
            ["Destination:", trip.destination],
            ["Origin:", trip.origin or "N/A"],
            ["Start Date:", PDFService.safe_strftime(trip.start_date, "%Y-%m-%d")],
            ["End Date:", PDFService.safe_strftime(trip.end_date, "%Y-%m-%d")],
            ["Duration:", f"{trip.duration_days} days"],
            ["Distance:", f"{trip.distance_km} km" if trip.distance_km else "N/A"],
            ["Transport:", trip.transport_type.title()],
            ["Travelers:", str(trip.number_of_travelers)],
        ]
        
        trip_table = Table(trip_data, colWidths=[2*inch, 4*inch])
        trip_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(trip_table)
        story.append(Spacer(1, 20))
        
        # Itinerary
        if trip.itinerary:
            story.append(Paragraph("Itinerary", heading_style))
            
            itinerary_data = [["Day", "Date", "Activities", "Accommodation"]]
            
            # Parse itinerary if it's a JSON string
            itinerary = trip.itinerary
            if isinstance(itinerary, str):
                try:
                    itinerary = json.loads(itinerary)
                except json.JSONDecodeError:
                    itinerary = []
            
            for item in itinerary:
                # Handle both dict and Pydantic model objects
                if hasattr(item, 'model_dump'):
                    # Pydantic model - convert to dict
                    item_dict = item.model_dump()
                elif hasattr(item, 'dict'):
                    # Older Pydantic model - convert to dict
                    item_dict = item.dict()
                elif isinstance(item, dict):
                    # Already a dict
                    item_dict = item
                else:
                    # Fallback - try to access attributes directly
                    item_dict = {
                        'day': getattr(item, 'day', ''),
                        'date': getattr(item, 'date', ''),
                        'activities': getattr(item, 'activities', []),
                        'accommodation': getattr(item, 'accommodation', 'N/A')
                    }
                
                activities = ", ".join(item_dict.get('activities', [])) if item_dict.get('activities') else "N/A"
                itinerary_data.append([
                    str(item_dict.get('day', '')),
                    item_dict.get('date', ''),
                    activities[:50] + "..." if len(activities) > 50 else activities,
                    item_dict.get('accommodation', 'N/A')
                ])
            
            itinerary_table = Table(itinerary_data, colWidths=[0.5*inch, 1*inch, 3*inch, 2.5*inch])
            itinerary_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('VALIGN', (0, 0), (-1, -1), 'TOP')
            ]))
            story.append(itinerary_table)
            story.append(Spacer(1, 30))
        
        # Cost Breakdown
        story.append(Paragraph("Cost Breakdown", heading_style))
        
        # Handle fare_breakdown - could be JSON string, dict, or Pydantic model
        fare_breakdown = trip.fare_breakdown
        if isinstance(fare_breakdown, str):
            try:
                fare_breakdown = json.loads(fare_breakdown)
            except json.JSONDecodeError:
                fare_breakdown = {}
        elif hasattr(fare_breakdown, 'model_dump'):
            # Pydantic v2 model - convert to dict
            fare_breakdown = fare_breakdown.model_dump()
        elif hasattr(fare_breakdown, 'dict'):
            # Pydantic v1 model - convert to dict
            fare_breakdown = fare_breakdown.dict()
        elif not isinstance(fare_breakdown, dict):
            # Fallback - try to access attributes directly
            fare_breakdown = {
                'transport_cost': getattr(fare_breakdown, 'transport_cost', 0),
                'accommodation_cost': getattr(fare_breakdown, 'accommodation_cost', 0),
                'meal_cost': getattr(fare_breakdown, 'meal_cost', 0),
                'activity_cost': getattr(fare_breakdown, 'activity_cost', 0),
                'guide_cost': getattr(fare_breakdown, 'guide_cost', 0),
                'misc_cost': getattr(fare_breakdown, 'misc_cost', 0),
                'service_charge': getattr(fare_breakdown, 'service_charge', 0),
                'tax_amount': getattr(fare_breakdown, 'tax_amount', 0),
                'discount': getattr(fare_breakdown, 'discount', 0),
            }
        
        cost_data = [
            ["Transport Cost:", f"${fare_breakdown.get('transport_cost', 0):.2f}"],
            ["Accommodation Cost:", f"${fare_breakdown.get('accommodation_cost', 0):.2f}"],
            ["Meal Cost:", f"${fare_breakdown.get('meal_cost', 0):.2f}"],
            ["Activity Cost:", f"${fare_breakdown.get('activity_cost', 0):.2f}"],
            ["Guide Cost:", f"${fare_breakdown.get('guide_cost', 0):.2f}"],
            ["Miscellaneous Cost:", f"${fare_breakdown.get('misc_cost', 0):.2f}"],
            ["Service Charge:", f"${fare_breakdown.get('service_charge', 0):.2f}"],
            ["Tax Amount:", f"${fare_breakdown.get('tax_amount', 0):.2f}"],
            ["Discount:", f"-${fare_breakdown.get('discount', 0):.2f}"],
        ]
        
        cost_table = Table(cost_data, colWidths=[3*inch, 2*inch])
        cost_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(cost_table)
        story.append(Spacer(1, 20))
        
        # Total
        total_data = [["TOTAL AMOUNT:", f"${trip.total_amount:.2f}"]]
        total_table = Table(total_data, colWidths=[3*inch, 2*inch])
        total_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.darkblue),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.whitesmoke),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 12),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ('GRID', (0, 0), (-1, -1), 2, colors.darkblue)
        ]))
        story.append(total_table)
        
        # Footer
        story.append(Spacer(1, 30))
        footer_text = """
        <para align=center>
        <b>Thank you for choosing our travel services!</b><br/>
        For any queries, please contact us at support@travelagency.com<br/>
        Generated on: {date}
        </para>
        """.format(date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        
        story.append(Paragraph(footer_text, styles['Normal']))
        
        # Build PDF
        doc.build(story)
        buffer.seek(0)
        return buffer.read()
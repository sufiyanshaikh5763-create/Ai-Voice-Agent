import type {
  AdminAppointment,
  AdminClientIntegration,
  AdminHealthDetails,
  AdminMonitoringRow,
  AdminToolCall,
  AdminWebhookEvent,
  AdminWebhookEventDetail,
  Appointment,
  ApptStatus,
  AppointmentHistoryItem,
  MockData,
} from './types';
import { dow } from './util';

// Demo data only. TODO(api): replace every array below with data from your backend.
const iso = '2026-10-20T09:00:00Z';
const ap = (id: string, cid: string, name: string, phone: string, date: string, time: string, service: string, status: ApptStatus, agent: string | undefined, staff: string | undefined, notes: string): Appointment => ({
  id, customer_id: cid, customer_name: name, customer_phone: phone, customer_email: name.split(' ')[0].toLowerCase() + '@mail.in',
  date, time, day_of_week: dow(date), service, status, agent_name: agent, staff_name: staff, notes, created_at: iso, updated_at: iso,
});
const h = (id: string, a: string, event: string, actor: string, type: 'staff' | 'ai_agent', old_value?: string, new_value?: string): AppointmentHistoryItem =>
  ({ id, appointment_id: a, event, old_value, new_value, actor, actor_type: type, timestamp: iso });

const cancelled = ap('a5', 'c5', 'Pooja Kale', '+91 98450 12345', '2026-10-23', '14:30:00', 'Hair spa', 'cancelled', 'Aria', undefined, 'Booked by phone.');
cancelled.cancel_reason = 'Caller asked to cancel.'; cancelled.cancelled_by = 'ai_agent';

export const MOCK: MockData = {
  appts: [
    ap('a1', 'c1', 'Ananya Deshmukh', '+91 98220 10001', '2026-10-26', '10:30:00', 'Dental check-up and cleaning', 'confirmed', 'Aria', undefined, 'Prefers a morning slot.'),
    ap('a2', 'c2', 'Rohan Patil', '+91 98220 10002', '2026-10-27', '16:00:00', 'Physiotherapy, first session', 'scheduled', undefined, 'Meera', 'Referred by Dr. Kulkarni.'),
    ap('a3', 'c3', 'Sneha Joshi', '+91 98220 10003', '2026-10-28', '11:15:00', 'Skin consultation', 'rescheduled', 'Aria', undefined, 'Moved from Oct 25 at her request.'),
    ap('a4', 'c4', 'Vikram Shinde', '+91 98220 10004', '2026-10-24', '09:00:00', 'Eye examination', 'completed', undefined, 'Ravi', 'Follow-up in 6 months.'),
    cancelled,
  ],
  history: {
    a1: [h('h1', 'a1', 'Booked by call', 'Aria', 'ai_agent'), h('h2', 'a1', 'Confirmed by SMS', 'Aria', 'ai_agent')],
    a2: [h('h3', 'a2', 'Booked by call', 'Aria', 'ai_agent')],
    a3: [h('h4', 'a3', 'Booked by call', 'Aria', 'ai_agent'), h('h5', 'a3', 'Rescheduled', 'Meera', 'staff', '2026-10-25', '2026-10-28')],
    a4: [h('h6', 'a4', 'Booked by call', 'Aria', 'ai_agent'), h('h7', 'a4', 'Marked completed', 'Ravi', 'staff')],
    a5: [h('h8', 'a5', 'Booked by call', 'Aria', 'ai_agent'), h('h9', 'a5', 'Cancelled', 'Aria', 'ai_agent')],
  },
  agents: [
    { id: 'g1', name: 'Aria', languages: 'English, Hindi', phone: '+91 20 4000 1101', online: true, calls_today: 42, business_id: 'b1', provider: 'sarvam', provider_agent_id: 'sarvam-sunrise-aria', status: 'active' },
    { id: 'g2', name: 'Veda', languages: 'Marathi, Hindi', phone: '+91 20 4000 1102', online: true, calls_today: 31, business_id: 'b1', provider: 'sarvam', provider_agent_id: 'sarvam-sunrise-veda', status: 'active' },
    { id: 'g3', name: 'Kiran', languages: 'English', phone: '+91 20 4000 1103', online: true, calls_today: 18, business_id: 'b1', provider: 'sarvam', provider_agent_id: 'sarvam-sunrise-kiran', status: 'active' },
    { id: 'g4', name: 'Nila', languages: 'English', phone: '+91 20 4000 2101', online: true, calls_today: 21, business_id: 'b2', provider: 'sarvam', provider_agent_id: 'sarvam-kale-nila', status: 'active' },
    { id: 'g5', name: 'Arjun', languages: 'Marathi, Hindi', phone: '+91 20 4000 3101', online: true, calls_today: 17, business_id: 'b3', provider: 'sarvam', provider_agent_id: 'sarvam-patil-arjun', status: 'active' },
    { id: 'g6', name: 'Isha', languages: 'English, Hindi', phone: '+91 20 4000 4101', online: false, calls_today: 0, business_id: 'b4', provider: 'sarvam', provider_agent_id: 'sarvam-brightpath-isha', status: 'inactive' },
  ],
  calls: [
    { id: 'k1', customer_name: 'Ananya Deshmukh', customer_phone: '+91 98220 10001', agent_name: 'Aria', duration_seconds: 134, status: 'completed', outcome: 'BOOKED', summary: 'Booked a dental check-up for Monday morning.', has_recording: true,
      transcript: [{ speaker: 'Aria', text: 'Namaste, Sunrise Dental, how can I help?', time: '0:00' }, { speaker: 'Caller', text: 'I need a check-up, Monday morning if possible.', time: '0:06' }, { speaker: 'Aria', text: 'Monday 10:30 is open. Shall I book it?', time: '0:12' }, { speaker: 'Caller', text: 'Yes please.', time: '0:16' }] },
    { id: 'k2', customer_name: 'Rahul Mane', customer_phone: '+91 98220 10010', agent_name: 'Veda', duration_seconds: 48, status: 'in_progress', summary: 'Caller is asking about root canal pricing.', has_recording: false,
      transcript: [{ speaker: 'Veda', text: 'Sunrise Dental, kasa madat karu?', time: '0:00' }, { speaker: 'Caller', text: 'Root canal cha kharcha kiti?', time: '0:05' }] },
    { id: 'k3', customer_name: 'Mahesh Pawar', customer_phone: '+91 98220 10011', agent_name: 'Veda', duration_seconds: 62, status: 'completed', outcome: 'INQUIRY', summary: 'Asked about clinic hours and parking.', has_recording: true,
      transcript: [{ speaker: 'Veda', text: 'Sunrise Dental, how can I help?', time: '0:00' }, { speaker: 'Caller', text: 'What time do you close, and is there parking?', time: '0:04' }] },
    { id: 'k4', customer_name: 'Unknown number', customer_phone: '+91 90000 00000', agent_name: 'Kiran', duration_seconds: 0, status: 'missed', summary: 'No answer: all agents were offline.', has_recording: false },
    { id: 'k5', customer_name: 'Sneha Joshi', customer_phone: '+91 98220 10003', agent_name: 'Aria', duration_seconds: 108, status: 'completed', outcome: 'BOOKED', summary: 'Rescheduled skin consultation to Wednesday.', has_recording: true,
      transcript: [{ speaker: 'Aria', text: 'Hello Sneha, calling about your Oct 25 slot?', time: '0:00' }, { speaker: 'Caller', text: 'Can we move it to Wednesday?', time: '0:05' }] },
  ],
  staff: [
    { id: 's1', name: 'Meera Kulkarni', title: 'Receptionist', days: [true, true, true, true, true, true, false] },
    { id: 's2', name: 'Ravi Jadhav', title: 'Dentist', days: [true, true, false, true, true, false, false] },
    { id: 's3', name: 'Neha Bhosale', title: 'Assistant', days: [false, true, true, true, true, true, false] },
  ],
  services: ['Check-up', 'Cleaning', 'Root canal', 'Whitening'],
  hours: [
    ...Array.from({ length: 5 }, () => ({ open: '09:00', close: '18:00', closed: false })),
    { open: '09:00', close: '14:00', closed: false }, { open: '00:00', close: '00:00', closed: true },
  ],
  businesses: [
    { id: 'b1', name: 'Sunrise Dental Care', plan: 'Growth', minutes_used: 186, minutes_limit: 300, status: 'Active', renews_on: '24 Nov 2026', last_login: 'Today 09:12', staff_pin: '1234' },
    { id: 'b2', name: 'Kale Wellness Studio', plan: 'Starter', minutes_used: 96, minutes_limit: 100, status: 'Active', renews_on: '02 Nov 2026', last_login: 'Yesterday', staff_pin: '2580' },
    { id: 'b3', name: 'Patil Auto Care', plan: 'Growth', minutes_used: 140, minutes_limit: 300, status: 'Active', renews_on: '30 Oct 2026', last_login: '2 days ago', staff_pin: '7391' },
    { id: 'b4', name: 'BrightPath Tuition', plan: 'Business', minutes_used: 640, minutes_limit: 700, status: 'Active', renews_on: '15 Nov 2026', last_login: 'Today 08:30', staff_pin: '' },
    { id: 'b5', name: 'Orbit Salon', plan: 'Starter', minutes_used: 12, minutes_limit: 100, status: 'Suspended', renews_on: '—', last_login: '9 days ago', staff_pin: '4410' },
  ],
  requests: [
    { id: 'r1', business: 'Sunrise Wellness', plan: 'Growth', billing: 'monthly', amount: 3499, status: 'Payment submitted' },
    { id: 'r2', business: 'Kale Yoga Studio', plan: 'Starter', billing: 'yearly', amount: 14990, status: 'Payment submitted' },
    { id: 'r3', business: 'BrightPath Coaching', plan: 'Business', billing: 'monthly', amount: 6999, status: 'Waiting for review' },
  ],
  messages: [
    { id: 'm1', name: 'Rahul Sharma', email: 'rahul@clinicmail.in', phone: '+91 98220 11002', message: 'Interested in the Growth plan for my two clinics. Can we get a demo this week?', received_at: '24 Oct, 09:40', read: false, handled: false },
    { id: 'm2', name: 'Priya Nair', email: 'priya@bloomsalon.in', phone: '+91 90110 55873', message: 'Does the agent speak Marathi? We get many local callers.', received_at: '23 Oct, 18:05', read: false, handled: false },
    { id: 'm3', name: 'Amit Gokhale', email: 'amit@gokhalelaw.in', phone: '+91 98500 77120', message: 'Please send the pricing for 700 minutes a month.', received_at: '22 Oct, 11:20', read: true, handled: true },
  ],
  logs: [
    { at: '24 Oct 15:58', text: 'Aria booked Ananya Deshmukh for Mon 10:30', level: 'info' },
    { at: '24 Oct 15:40', text: 'Kale Wellness Studio used 96% of its minutes', level: 'warn' },
    { at: '24 Oct 15:12', text: 'Calendar sync retry failed for Patil Auto Care', level: 'error' },
    { at: '24 Oct 14:50', text: 'Access request from BrightPath Coaching reviewed', level: 'info' },
    { at: '24 Oct 09:12', text: 'Sunrise Dental Care admin signed in', level: 'info' },
  ],
};

const mockIntegration = (clientId: string): AdminClientIntegration => ({
  signed_event_webhook_url: '/api/v1/webhooks/sarvam',
  tool_url_patterns: Object.fromEntries(
    ['check-slot', 'book', 'reschedule', 'cancel'].map((action) => [
      action,
      `/api/v1/webhooks/sarvam/{TOKEN}/${clientId}/appointments/${action}`,
    ]),
  ),
  urls_are_absolute: false,
  credential_exists: false,
  credential_created_at: null,
  credential_rotated_at: null,
  credential_last_used_at: null,
  agents: [],
});

export const MOCK_CLIENT_INTEGRATIONS: Record<string, AdminClientIntegration> = {
  b1: mockIntegration('b1'),
  b2: mockIntegration('b2'),
  b3: mockIntegration('b3'),
  b4: mockIntegration('b4'),
  b5: mockIntegration('b5'),
};

const webhookEvents: AdminWebhookEvent[] = [
  { id: 301, provider: 'sarvam', event_id: 'evt_demo_301', event_type: 'call.completed', client_id: 2, business_name: 'Kale Wellness Studio', status: 'failed', error_message: 'Appointment slot is no longer available.', created_at: '2026-10-24T15:40:00Z', processed_at: '2026-10-24T15:40:01Z' },
  { id: 300, provider: 'sarvam', event_id: 'evt_demo_300', event_type: 'call.completed', client_id: 1, business_name: 'Sunrise Dental Care', status: 'processed', error_message: null, created_at: '2026-10-24T15:12:00Z', processed_at: '2026-10-24T15:12:02Z' },
  { id: 299, provider: 'sarvam', event_id: 'evt_demo_299', event_type: 'call.started', client_id: null, business_name: null, status: 'failed', error_message: 'Unknown agent: ag_demo_unknown', created_at: '2026-10-24T14:50:00Z', processed_at: '2026-10-24T14:50:00Z' },
  { id: 298, provider: 'sarvam', event_id: 'evt_demo_298', event_type: 'call.completed', client_id: 3, business_name: 'Patil Auto Care', status: 'duplicate', error_message: null, created_at: '2026-10-24T14:20:00Z', processed_at: '2026-10-24T14:20:00Z' },
  ...Array.from({ length: 8 }, (_, index): AdminWebhookEvent => ({
    id: 297 - index, provider: 'sarvam', event_id: `evt_demo_${297 - index}`, event_type: 'call.completed',
    client_id: (index % 4) + 1, business_name: ['Sunrise Dental Care', 'Kale Wellness Studio', 'Patil Auto Care', 'BrightPath Tuition'][index % 4],
    status: index % 3 === 0 ? 'processed' : 'received', error_message: null,
    created_at: `2026-10-23T${String(18 - index).padStart(2, '0')}:00:00Z`,
    processed_at: index % 3 === 0 ? `2026-10-23T${String(18 - index).padStart(2, '0')}:00:02Z` : null,
  })),
];

const webhookEventDetails: Record<number, AdminWebhookEventDetail> = {
  301: { ...webhookEvents[0], payload: { event: 'call.completed', caller: { name: 'Riya Shah', phone: '******1234' }, tool: { name: 'book', arguments: { service: 'Consultation', phone: '******1234' } } } },
  300: { ...webhookEvents[1], payload: { event: 'call.completed', caller: { name: 'Ananya Deshmukh', phone: '******1001' }, result: { outcome: 'appointment_booked' } } },
  299: { ...webhookEvents[2], payload: { event: 'call.started', agent: { id: 'ag_demo_unknown' }, caller: { phone: '******5678' } } },
  298: { ...webhookEvents[3], payload: { event: 'call.completed', status: 'duplicate' } },
};
for (const event of webhookEvents) {
  if (!webhookEventDetails[event.id]) {
    webhookEventDetails[event.id] = {
      ...event,
      payload: { event: event.event_type, caller: { phone: '******4321' }, status: event.status },
    };
  }
}

const toolCalls: AdminToolCall[] = [
  { id: 501, client_id: 2, business_name: 'Kale Wellness Studio', tool: 'book', action: 'sarvam_tool.book', tenant_resolution: 'resolved', success: false, error_code: 'SLOT_TAKEN', message: 'The requested time slot is no longer available.', appointment_id: null, duration_ms: 84, request_id: 'req_demo_501', created_at: '2026-10-24T15:40:01Z' },
  { id: 500, client_id: 1, business_name: 'Sunrise Dental Care', tool: 'book', action: 'sarvam_tool.book', tenant_resolution: 'resolved', success: true, error_code: null, message: null, appointment_id: 901, duration_ms: 126, request_id: 'req_demo_500', created_at: '2026-10-24T15:12:02Z' },
  { id: 499, client_id: null, business_name: null, tool: 'book', action: 'sarvam_tool.book', tenant_resolution: 'unresolved', success: false, error_code: 'CLIENT_NOT_FOUND', message: 'Client could not be resolved.', appointment_id: null, duration_ms: 19, request_id: 'req_demo_499', created_at: '2026-10-24T14:50:00Z' },
  { id: 498, client_id: 3, business_name: 'Patil Auto Care', tool: 'check-slot', action: 'sarvam_tool.check_slot', tenant_resolution: 'resolved', success: true, error_code: null, message: null, appointment_id: null, duration_ms: 38, request_id: 'req_demo_498', created_at: '2026-10-24T14:20:00Z' },
  ...Array.from({ length: 8 }, (_, index): AdminToolCall => ({
    id: 497 - index, client_id: (index % 4) + 1,
    business_name: ['Sunrise Dental Care', 'Kale Wellness Studio', 'Patil Auto Care', 'BrightPath Tuition'][index % 4],
    tool: ['check-slot', 'book', 'reschedule', 'cancel'][index % 4],
    action: ['sarvam_tool.check_slot', 'sarvam_tool.book', 'sarvam_tool.reschedule', 'sarvam_tool.cancel'][index % 4],
    tenant_resolution: 'resolved', success: index % 3 !== 0, error_code: index % 3 === 0 ? 'SLOT_TAKEN' : null,
    message: index % 3 === 0 ? 'The requested time slot is no longer available.' : null,
    appointment_id: index % 3 === 0 ? null : 890 - index, duration_ms: 42 + index * 9,
    request_id: `req_demo_${497 - index}`, created_at: `2026-10-23T${String(18 - index).padStart(2, '0')}:00:00Z`,
  })),
];

const appointments: AdminAppointment[] = [
  { id: 901, client_id: 1, business_name: 'Sunrise Dental Care', customer_name: 'Ananya Deshmukh', date: '2026-10-27', time: '10:30:00', status: 'confirmed', source: 'ai_agent', created_at: '2026-10-24T15:12:02Z' },
  { id: 900, client_id: 2, business_name: 'Kale Wellness Studio', customer_name: 'Riya Shah', date: '2026-10-28', time: '14:00:00', status: 'scheduled', source: 'manual', created_at: '2026-10-24T13:08:00Z' },
  { id: 899, client_id: 3, business_name: 'Patil Auto Care', customer_name: 'Amit Patil', date: '2026-10-29', time: '09:30:00', status: 'cancelled', source: 'ai_agent', created_at: '2026-10-23T12:30:00Z' },
  { id: 898, client_id: 4, business_name: 'BrightPath Tuition', customer_name: 'Neha Kulkarni', date: '2026-10-30', time: '16:00:00', status: 'confirmed', source: 'manual', created_at: '2026-10-22T11:15:00Z' },
  ...Array.from({ length: 8 }, (_, index): AdminAppointment => ({
    id: 897 - index, client_id: (index % 4) + 1,
    business_name: ['Sunrise Dental Care', 'Kale Wellness Studio', 'Patil Auto Care', 'BrightPath Tuition'][index % 4],
    customer_name: ['Maya Joshi', 'Aarav Kulkarni', 'Ira Patil', 'Kabir Shah'][index % 4],
    date: `2026-10-${String(31 - (index % 6)).padStart(2, '0')}`, time: `${String(9 + index).padStart(2, '0')}:00:00`,
    status: ['scheduled', 'confirmed', 'completed', 'cancelled'][index % 4],
    source: index % 2 ? 'manual' : 'ai_agent',
    created_at: `2026-10-21T${String(18 - index).padStart(2, '0')}:00:00Z`,
  })),
];

const monitoring: AdminMonitoringRow[] = [
  { client_id: 1, business_name: 'Sunrise Dental Care', access_status: 'active', agent_status: 'active', provider_agent_id_present: true, last_call_time: '2026-10-24T15:12:00Z', minutes_used: 186, minutes_limit: 300, usage_percent: 62, alert: 'none', failed_webhook_events_24h: 0, last_webhook_received_at: '2026-10-24T15:12:00Z', last_tool_call_at: '2026-10-24T15:12:02Z', last_tool_call_error: null },
  { client_id: 2, business_name: 'Kale Wellness Studio', access_status: 'active', agent_status: 'active', provider_agent_id_present: true, last_call_time: '2026-10-24T15:40:00Z', minutes_used: 96, minutes_limit: 100, usage_percent: 96, alert: 'warning', failed_webhook_events_24h: 2, last_webhook_received_at: '2026-10-24T15:40:00Z', last_tool_call_at: '2026-10-24T15:40:01Z', last_tool_call_error: 'SLOT_TAKEN' },
  { client_id: 3, business_name: 'Patil Auto Care', access_status: 'active', agent_status: 'inactive', provider_agent_id_present: false, last_call_time: null, minutes_used: 312, minutes_limit: 300, usage_percent: 104, alert: 'limit', failed_webhook_events_24h: 1, last_webhook_received_at: '2026-10-24T14:50:00Z', last_tool_call_at: '2026-10-24T14:20:00Z', last_tool_call_error: null },
  { client_id: 4, business_name: 'BrightPath Tuition', access_status: 'active', agent_status: null, provider_agent_id_present: false, last_call_time: null, minutes_used: 0, minutes_limit: 700, usage_percent: 0, alert: 'none', failed_webhook_events_24h: 0, last_webhook_received_at: null, last_tool_call_at: null, last_tool_call_error: null },
];

const health: AdminHealthDetails = {
  database_ok: true,
  last_webhook_received_at: '2026-10-24T15:40:00Z',
  sarvam_api_key_set: true,
  sarvam_base_url_set: true,
  sarvam_webhook_secret_set: true,
  email_backend: 'resend',
  resend_api_key_set: true,
  app_env_production: false,
};

export const MOCK_LOGWATCH = { webhookEvents, webhookEventDetails, toolCalls, appointments, monitoring, health };

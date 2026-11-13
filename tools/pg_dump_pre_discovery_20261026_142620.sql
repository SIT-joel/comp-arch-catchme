--
-- PostgreSQL database dump
--

\restrict hVFeGv6Xd5VxlC9cRAhjtoFzdTZpukhs7uPytZPQkILH7pdStuVkKtF60IcXZcb

-- Dumped from database version 17.11
-- Dumped by pg_dump version 17.11

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: catch_me
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


ALTER TABLE public.alembic_version OWNER TO catch_me;

--
-- Name: app_state; Type: TABLE; Schema: public; Owner: catch_me
--

CREATE TABLE public.app_state (
    key character varying(32) NOT NULL,
    value bigint NOT NULL
);


ALTER TABLE public.app_state OWNER TO catch_me;

--
-- Name: devices; Type: TABLE; Schema: public; Owner: catch_me
--

CREATE TABLE public.devices (
    id uuid NOT NULL,
    owner_user_id uuid,
    name character varying(64) NOT NULL,
    firmware_alias integer NOT NULL,
    pairing_code_hash character varying(256),
    claimed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


ALTER TABLE public.devices OWNER TO catch_me;

--
-- Name: login_sessions; Type: TABLE; Schema: public; Owner: catch_me
--

CREATE TABLE public.login_sessions (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    token_hash character varying(128) NOT NULL,
    csrf_token character varying(128) NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    revoked_at timestamp with time zone
);


ALTER TABLE public.login_sessions OWNER TO catch_me;

--
-- Name: owned_rewards; Type: TABLE; Schema: public; Owner: catch_me
--

CREATE TABLE public.owned_rewards (
    user_id uuid NOT NULL,
    reward_id character varying(32) NOT NULL,
    acquired_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


ALTER TABLE public.owned_rewards OWNER TO catch_me;

--
-- Name: pairings; Type: TABLE; Schema: public; Owner: catch_me
--

CREATE TABLE public.pairings (
    id uuid NOT NULL,
    user_a_id uuid NOT NULL,
    user_b_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT ck_pairings_ordered CHECK ((user_a_id < user_b_id))
);


ALTER TABLE public.pairings OWNER TO catch_me;

--
-- Name: point_transactions; Type: TABLE; Schema: public; Owner: catch_me
--

CREATE TABLE public.point_transactions (
    id bigint NOT NULL,
    user_id uuid NOT NULL,
    kind character varying(32) NOT NULL,
    delta integer NOT NULL,
    xp_delta integer NOT NULL,
    balance_after integer NOT NULL,
    session_id uuid,
    reward_id character varying(32),
    idempotency_key character varying(128),
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT ck_tx_nonzero CHECK ((delta <> 0))
);


ALTER TABLE public.point_transactions OWNER TO catch_me;

--
-- Name: point_transactions_id_seq; Type: SEQUENCE; Schema: public; Owner: catch_me
--

CREATE SEQUENCE public.point_transactions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.point_transactions_id_seq OWNER TO catch_me;

--
-- Name: point_transactions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: catch_me
--

ALTER SEQUENCE public.point_transactions_id_seq OWNED BY public.point_transactions.id;


--
-- Name: quest_awards; Type: TABLE; Schema: public; Owner: catch_me
--

CREATE TABLE public.quest_awards (
    id uuid NOT NULL,
    session_id uuid NOT NULL,
    user_id uuid NOT NULL,
    points integer NOT NULL,
    xp integer NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


ALTER TABLE public.quest_awards OWNER TO catch_me;

--
-- Name: quest_sessions; Type: TABLE; Schema: public; Owner: catch_me
--

CREATE TABLE public.quest_sessions (
    id uuid NOT NULL,
    quest_id character varying(32) NOT NULL,
    demo boolean NOT NULL,
    state character varying(16) NOT NULL,
    created_by uuid NOT NULL,
    target_ms integer,
    session_token character varying(64),
    geofence_lat double precision,
    geofence_lon double precision,
    geofence_radius_m double precision,
    progress_ms integer NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    activated_at timestamp with time zone,
    completed_at timestamp with time zone,
    cancelled_at timestamp with time zone,
    CONSTRAINT ck_sessions_state CHECK (((state)::text = ANY ((ARRAY['pending'::character varying, 'active'::character varying, 'completed'::character varying, 'cancelled'::character varying])::text[])))
);


ALTER TABLE public.quest_sessions OWNER TO catch_me;

--
-- Name: rewards; Type: TABLE; Schema: public; Owner: catch_me
--

CREATE TABLE public.rewards (
    id character varying(32) NOT NULL,
    name character varying(64) NOT NULL,
    description character varying(256) NOT NULL,
    price integer NOT NULL
);


ALTER TABLE public.rewards OWNER TO catch_me;

--
-- Name: session_participants; Type: TABLE; Schema: public; Owner: catch_me
--

CREATE TABLE public.session_participants (
    session_id uuid NOT NULL,
    user_id uuid NOT NULL,
    accepted_at timestamp with time zone
);


ALTER TABLE public.session_participants OWNER TO catch_me;

--
-- Name: telemetry_records; Type: TABLE; Schema: public; Owner: catch_me
--

CREATE TABLE public.telemetry_records (
    id bigint NOT NULL,
    device_id uuid NOT NULL,
    boot_id character varying(64) NOT NULL,
    sequence bigint NOT NULL,
    session_id uuid,
    uptime_ms bigint NOT NULL,
    captured_at timestamp with time zone,
    clock_source character varying(32) NOT NULL,
    clock_uncertainty_ms integer,
    gps_valid boolean NOT NULL,
    gps_lat double precision,
    gps_lon double precision,
    gps_fix_age_ms integer,
    hr_valid boolean NOT NULL,
    bpm integer,
    hr_status character varying(16),
    peer_observed boolean NOT NULL,
    peer_device_id uuid,
    peer_boot_id character varying(64),
    peer_heartbeat_sequence bigint,
    peer_session_token character varying(64),
    peer_observation_age_ms integer,
    received_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


ALTER TABLE public.telemetry_records OWNER TO catch_me;

--
-- Name: telemetry_records_id_seq; Type: SEQUENCE; Schema: public; Owner: catch_me
--

CREATE SEQUENCE public.telemetry_records_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.telemetry_records_id_seq OWNER TO catch_me;

--
-- Name: telemetry_records_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: catch_me
--

ALTER SEQUENCE public.telemetry_records_id_seq OWNED BY public.telemetry_records.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: catch_me
--

CREATE TABLE public.users (
    id uuid NOT NULL,
    username character varying(64) NOT NULL,
    password_hash character varying(256) NOT NULL,
    display_name character varying(64) NOT NULL,
    points_balance integer NOT NULL,
    lifetime_xp integer NOT NULL,
    location_sharing boolean NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


ALTER TABLE public.users OWNER TO catch_me;

--
-- Name: point_transactions id; Type: DEFAULT; Schema: public; Owner: catch_me
--

ALTER TABLE ONLY public.point_transactions ALTER COLUMN id SET DEFAULT nextval('public.point_transactions_id_seq'::regclass);


--
-- Name: telemetry_records id; Type: DEFAULT; Schema: public; Owner: catch_me
--

ALTER TABLE ONLY public.telemetry_records ALTER COLUMN id SET DEFAULT nextval('public.telemetry_records_id_seq'::regclass);


--
-- Data for Name: alembic_version; Type: TABLE DATA; Schema: public; Owner: catch_me
--

COPY public.alembic_version (version_num) FROM stdin;
58a9a37d73d0
\.


--
-- Data for Name: app_state; Type: TABLE DATA; Schema: public; Owner: catch_me
--

COPY public.app_state (key, value) FROM stdin;
state_version	296
\.


--
-- Data for Name: devices; Type: TABLE DATA; Schema: public; Owner: catch_me
--

COPY public.devices (id, owner_user_id, name, firmware_alias, pairing_code_hash, claimed_at, created_at) FROM stdin;
904229f7-6dee-5ce6-85cb-51227471b2f4	9a032bc0-bbdf-5167-af46-0e0882a7db09	Wearable 1	1	\N	2026-10-25 01:37:10.516235+00	2026-10-24 19:46:56.185741+00
cc018d28-8d17-5e40-b42f-bdb79c40758c	8c52d6e8-0d44-52d4-91d0-e05fefbb572e	Wearable 2	2	\N	2026-10-25 01:37:10.542789+00	2026-10-24 19:46:56.185741+00
\.


--
-- Data for Name: login_sessions; Type: TABLE DATA; Schema: public; Owner: catch_me
--

COPY public.login_sessions (id, user_id, token_hash, csrf_token, created_at, expires_at, revoked_at) FROM stdin;
c8bdf1fb-054a-4692-8789-768a1374af60	9a032bc0-bbdf-5167-af46-0e0882a7db09	373ec866a8dca5d87ea44c1b1b18925edcc40aa601de4484d3196c4388ebb31f	0b79cb51438b19d36d2a888d7d1927d25c3ce3bd72e0b16d34e0d8bc8666ef12	2026-10-25 01:36:06.985907+00	2026-11-01 01:36:07.085125+00	\N
9a60f068-4181-4ce5-b933-fd47e3fb82df	9a032bc0-bbdf-5167-af46-0e0882a7db09	52a42ef2d1b5137d6e7989a3aeda5a58fecfc942fc3f09fa044f1732bb9a4ef0	276608c03b5cde95f8f6448dc3bab08fba6c1264a5da37bf4fa5e457c7c7dbdd	2026-10-25 01:36:49.39076+00	2026-11-01 01:36:49.486768+00	\N
b0eb58c7-7122-4883-87af-a4cf2bbd727b	8c52d6e8-0d44-52d4-91d0-e05fefbb572e	6124431528b5366306213604209f4ddaa6f4baa9e94d6c84b741f1972325fc95	7cf2b1f5d59225ac78f1dd898c43825c830345f401056fa0b1db7def5cddcc00	2026-10-25 01:36:49.504005+00	2026-11-01 01:36:49.62638+00	\N
d7a35693-a497-4946-b5df-f18ddb10f3e9	9a032bc0-bbdf-5167-af46-0e0882a7db09	1b2936e075ab30126309227e1040582ee341ef3abff2a594cdbf91b004dfe8bf	0682e9c509621ae0f080aee1146d867351c1744f7150e9ccfeb68a430c4dae3b	2026-10-25 01:37:10.272277+00	2026-11-01 01:37:10.366609+00	\N
6bfb6e16-01db-4c07-8186-c7abda75faa6	8c52d6e8-0d44-52d4-91d0-e05fefbb572e	4ee9f36c913886376867142ed4c82dc0b0a388a9110e3e253fd6956722914ad0	7e8102feb62208bdab1616426fafc9402db8a27c3eda5dfdb09ca1f9114d9328	2026-10-25 01:37:10.38336+00	2026-11-01 01:37:10.478264+00	\N
fba2041b-066c-4606-914d-9d05bc0c9c23	9a032bc0-bbdf-5167-af46-0e0882a7db09	88f2dd41a6fb80f019d30e06cdad838b96127a498838c366ac6a4e7aab1b3b11	d9ef5b9845808f9751328f53bf4e7bcccb5245c292de9f9db993d330a0ceeb4f	2026-10-25 01:37:19.358964+00	2026-11-01 01:37:19.47164+00	\N
e707ab4f-b6d4-47e4-b927-61daf619d9fe	9a032bc0-bbdf-5167-af46-0e0882a7db09	3f682c4d1960268e00977f62c0f1bba67e75ac6de108d7e13d21a2a1cbaef235	24df3a51a48cd35ad527fb737183d1d9687b0092980a8c576a8e470050c9e68e	2026-10-25 01:37:36.036563+00	2026-11-01 01:37:36.134622+00	\N
0079e7c3-325d-4f17-8499-a08ae0378ca2	8c52d6e8-0d44-52d4-91d0-e05fefbb572e	8223551cc21ba34f618d54880e5b4ce923cc26011ea391911fcf44e8465b882c	afeeccfb7993533f6bc815805a86f744f5ed0cfd7d66e0c9750d906bacc15bb1	2026-10-25 01:37:36.15324+00	2026-11-01 01:37:36.247909+00	\N
fe9a77c3-0fcb-4d3f-9a9e-9313bdab7e6d	9a032bc0-bbdf-5167-af46-0e0882a7db09	ca6cf7a4baeb395ce832f4e1306c9472eb4b3355eb2fc2b195857e62b0d89c46	c494ad264a68b4c88370215a2dec357d619ff8640c3bda7832b6f588e87cb2a0	2026-10-25 01:38:04.316229+00	2026-11-01 01:38:04.415487+00	\N
f67e53d4-61e0-4424-a0e6-4d85a3f263f8	8c52d6e8-0d44-52d4-91d0-e05fefbb572e	38987a34f8774e8b094c8ff84843dbf27331f7b20634fa1828de6bc8e439234a	f2a310fa83bf0cf9c2e359c99dbf6c5765d9904ca577c1cb458918babe8ab2af	2026-10-25 01:38:04.433682+00	2026-11-01 01:38:04.52959+00	\N
1259f6fe-3754-490e-9388-fb0fb44fef66	9a032bc0-bbdf-5167-af46-0e0882a7db09	deb660ddba27fe333b718620069b20415427d87e21edb99ee7aed0d2cde9470c	84940336600dfea15537e337a71b7aeebadca7e20d9e7b3f65c438f94df70b93	2026-10-25 01:40:01.707417+00	2026-11-01 01:40:01.807205+00	\N
59e5eff5-704d-4542-a17f-7694a9c89f28	8c52d6e8-0d44-52d4-91d0-e05fefbb572e	25b1072f0b239a1fd2260a004c06a066b95518536f00a5081ced406f638b1243	513921653f9a8aa95324669ab95e6fa1a449e1d4735b4393b89aad006476b140	2026-10-25 01:40:01.824634+00	2026-11-01 01:40:01.920796+00	\N
3353ec87-202d-46be-9023-3c44f306ddd0	9a032bc0-bbdf-5167-af46-0e0882a7db09	d56ebf089dd029cc1a78f6898f0303fe803efef6b53b3d25448e6f57e0935dd3	2a10d5d8cf3e0817c0d419b78f2c4848400e4863f2f3e8aa6f08328d5f0db8d3	2026-10-25 12:29:29.011818+00	2026-11-01 12:29:29.175742+00	\N
50b12eb4-3c7e-4132-9ffd-05611d3e6c6d	9a032bc0-bbdf-5167-af46-0e0882a7db09	c1c8630050e45dd07b2e3825992afbe5ce9a99a3a79291ad080415afcb9cb55e	8e6b2dddf3e76b317a72c539512ff2401714c68bf283f3e87e8d34462e41dc02	2026-10-25 15:54:59.116143+00	2026-11-01 15:54:59.274132+00	\N
d100219a-2a5a-40ef-8f14-c79d01cce454	9a032bc0-bbdf-5167-af46-0e0882a7db09	619d8897e1ff7e3762a679857066fe8029b813601d70e127cb4a025e8a0456da	9c793ec210c009fad257b0844cdeb775956df8d56adfd43ce6d2f654933f1f84	2026-10-25 15:57:56.60886+00	2026-11-01 15:57:56.776861+00	\N
84faa5ce-e3f7-489d-864b-f01392950820	9a032bc0-bbdf-5167-af46-0e0882a7db09	c0a80a4431ca803beeb86e883aef376fad24a15f2521b8b6ac471362594ac53f	ced28919db52819fee6584fa6370231ed21e24409ec2d61fd9cca80fca8cd999	2026-10-25 15:59:52.980375+00	2026-11-01 15:59:53.180317+00	\N
22469568-443b-473a-8f3e-1ab40dd5f5c9	9a032bc0-bbdf-5167-af46-0e0882a7db09	096806f40262afdceba5b07ff9fae5b0316417a9cabf2c6093a14241d62824f4	f54052a0de5e85a9966b191aa77419294b8a8d7d89472b32612a931fe1e1b9e6	2026-10-25 16:08:34.776262+00	2026-11-01 16:08:34.928598+00	\N
b116a6cd-b958-424c-a298-9c9151830a20	9a032bc0-bbdf-5167-af46-0e0882a7db09	62d0cf891b32f5224b4cd749d4226607cdf639bbf2b4a85bcb6db9fadb920a4c	737e3243c1819e9f6722fc99c8e998410dceac4aefe2ce754bf31e5aecee708a	2026-10-25 17:33:42.869919+00	2026-11-01 17:33:43.018265+00	\N
\.


--
-- Data for Name: owned_rewards; Type: TABLE DATA; Schema: public; Owner: catch_me
--

COPY public.owned_rewards (user_id, reward_id, acquired_at) FROM stdin;
9a032bc0-bbdf-5167-af46-0e0882a7db09	first_spark	2026-10-25 01:40:02.806776+00
\.


--
-- Data for Name: pairings; Type: TABLE DATA; Schema: public; Owner: catch_me
--

COPY public.pairings (id, user_a_id, user_b_id, created_at) FROM stdin;
98a3e8c9-1136-5d8c-953d-219f72f2cd31	8c52d6e8-0d44-52d4-91d0-e05fefbb572e	9a032bc0-bbdf-5167-af46-0e0882a7db09	2026-10-24 19:46:56.185741+00
\.


--
-- Data for Name: point_transactions; Type: TABLE DATA; Schema: public; Owner: catch_me
--

COPY public.point_transactions (id, user_id, kind, delta, xp_delta, balance_after, session_id, reward_id, idempotency_key, created_at) FROM stdin;
1	9a032bc0-bbdf-5167-af46-0e0882a7db09	quest_award	100	100	100	c1a155eb-bfff-41ac-954b-6314433a952b	\N	\N	2026-10-25 01:40:02.742615+00
2	8c52d6e8-0d44-52d4-91d0-e05fefbb572e	quest_award	100	100	100	c1a155eb-bfff-41ac-954b-6314433a952b	\N	\N	2026-10-25 01:40:02.742615+00
3	9a032bc0-bbdf-5167-af46-0e0882a7db09	purchase	-50	0	50	\N	first_spark	e2e-c1a155eb	2026-10-25 01:40:02.806776+00
\.


--
-- Data for Name: quest_awards; Type: TABLE DATA; Schema: public; Owner: catch_me
--

COPY public.quest_awards (id, session_id, user_id, points, xp, created_at) FROM stdin;
71eeeaa9-9529-41a4-ace4-dc1ffd021af7	c1a155eb-bfff-41ac-954b-6314433a952b	9a032bc0-bbdf-5167-af46-0e0882a7db09	100	100	2026-10-25 01:40:02.742615+00
0851e5dc-521f-4d68-8bc8-d00c19ff95a9	c1a155eb-bfff-41ac-954b-6314433a952b	8c52d6e8-0d44-52d4-91d0-e05fefbb572e	100	100	2026-10-25 01:40:02.742615+00
\.


--
-- Data for Name: quest_sessions; Type: TABLE DATA; Schema: public; Owner: catch_me
--

COPY public.quest_sessions (id, quest_id, demo, state, created_by, target_ms, session_token, geofence_lat, geofence_lon, geofence_radius_m, progress_ms, created_at, activated_at, completed_at, cancelled_at) FROM stdin;
c1a155eb-bfff-41ac-954b-6314433a952b	together	t	completed	9a032bc0-bbdf-5167-af46-0e0882a7db09	30000	W_eUon_Ot2Y_K3xYzQ1jWoY_R2sRTE2g	\N	\N	\N	30000	2026-10-25 01:40:01.974273+00	2026-10-25 01:40:02.006588+00	2026-10-25 01:39:01.627934+00	\N
30f11f19-c0bf-4c64-a167-6a0ec697e18b	heart_challenge	t	pending	9a032bc0-bbdf-5167-af46-0e0882a7db09	\N	\N	\N	\N	\N	0	2026-10-25 18:43:12.84211+00	\N	\N	\N
\.


--
-- Data for Name: rewards; Type: TABLE DATA; Schema: public; Owner: catch_me
--

COPY public.rewards (id, name, description, price) FROM stdin;
first_spark	First Spark	Complete your first shared quest together.	50
adventure_pair	Adventure Pair	Finish an outdoor geofence visit together.	100
heart_duo	Heart Duo	Complete a heart challenge with valid readings on both wearables.	200
\.


--
-- Data for Name: session_participants; Type: TABLE DATA; Schema: public; Owner: catch_me
--

COPY public.session_participants (session_id, user_id, accepted_at) FROM stdin;
c1a155eb-bfff-41ac-954b-6314433a952b	9a032bc0-bbdf-5167-af46-0e0882a7db09	2026-10-25 01:40:01.984251+00
c1a155eb-bfff-41ac-954b-6314433a952b	8c52d6e8-0d44-52d4-91d0-e05fefbb572e	2026-10-25 01:40:02.006575+00
30f11f19-c0bf-4c64-a167-6a0ec697e18b	9a032bc0-bbdf-5167-af46-0e0882a7db09	2026-10-25 18:43:12.856285+00
30f11f19-c0bf-4c64-a167-6a0ec697e18b	8c52d6e8-0d44-52d4-91d0-e05fefbb572e	\N
\.


--
-- Data for Name: telemetry_records; Type: TABLE DATA; Schema: public; Owner: catch_me
--

COPY public.telemetry_records (id, device_id, boot_id, sequence, session_id, uptime_ms, captured_at, clock_source, clock_uncertainty_ms, gps_valid, gps_lat, gps_lon, gps_fix_age_ms, hr_valid, bpm, hr_status, peer_observed, peer_device_id, peer_boot_id, peer_heartbeat_sequence, peer_session_token, peer_observation_age_ms, received_at) FROM stdin;
1	904229f7-6dee-5ce6-85cb-51227471b2f4	boot-2	1	c1a155eb-bfff-41ac-954b-6314433a952b	0	2026-10-25 01:38:31.627934+00	phone_server_anchor	300	f	\N	\N	\N	f	\N	no_contact	t	cc018d28-8d17-5e40-b42f-bdb79c40758c	boot-2	1	W_eUon_Ot2Y_K3xYzQ1jWoY_R2sRTE2g	0	2026-10-25 01:40:02.023443+00
2	cc018d28-8d17-5e40-b42f-bdb79c40758c	boot-1	1	c1a155eb-bfff-41ac-954b-6314433a952b	0	2026-10-25 01:38:31.627934+00	phone_server_anchor	300	f	\N	\N	\N	f	\N	no_contact	t	904229f7-6dee-5ce6-85cb-51227471b2f4	boot-1	1	W_eUon_Ot2Y_K3xYzQ1jWoY_R2sRTE2g	0	2026-10-25 01:40:02.052866+00
3	904229f7-6dee-5ce6-85cb-51227471b2f4	boot-2	2	c1a155eb-bfff-41ac-954b-6314433a952b	2000	2026-10-25 01:38:33.627934+00	phone_server_anchor	300	f	\N	\N	\N	f	\N	no_contact	t	cc018d28-8d17-5e40-b42f-bdb79c40758c	boot-2	2	W_eUon_Ot2Y_K3xYzQ1jWoY_R2sRTE2g	0	2026-10-25 01:40:02.076532+00
4	cc018d28-8d17-5e40-b42f-bdb79c40758c	boot-1	2	c1a155eb-bfff-41ac-954b-6314433a952b	2000	2026-10-25 01:38:33.627934+00	phone_server_anchor	300	f	\N	\N	\N	f	\N	no_contact	t	904229f7-6dee-5ce6-85cb-51227471b2f4	boot-1	2	W_eUon_Ot2Y_K3xYzQ1jWoY_R2sRTE2g	0	2026-10-25 01:40:02.099656+00
5	904229f7-6dee-5ce6-85cb-51227471b2f4	boot-2	3	c1a155eb-bfff-41ac-954b-6314433a952b	4000	2026-10-25 01:38:35.627934+00	phone_server_anchor	300	f	\N	\N	\N	f	\N	no_contact	t	cc018d28-8d17-5e40-b42f-bdb79c40758c	boot-2	3	W_eUon_Ot2Y_K3xYzQ1jWoY_R2sRTE2g	0	2026-10-25 01:40:02.122881+00
6	cc018d28-8d17-5e40-b42f-bdb79c40758c	boot-1	3	c1a155eb-bfff-41ac-954b-6314433a952b	4000	2026-10-25 01:38:35.627934+00	phone_server_anchor	300	f	\N	\N	\N	f	\N	no_contact	t	904229f7-6dee-5ce6-85cb-51227471b2f4	boot-1	3	W_eUon_Ot2Y_K3xYzQ1jWoY_R2sRTE2g	0	2026-10-25 01:40:02.145813+00
7	904229f7-6dee-5ce6-85cb-51227471b2f4	boot-2	4	c1a155eb-bfff-41ac-954b-6314433a952b	6000	2026-10-25 01:38:37.627934+00	phone_server_anchor	300	f	\N	\N	\N	f	\N	no_contact	t	cc018d28-8d17-5e40-b42f-bdb79c40758c	boot-2	4	W_eUon_Ot2Y_K3xYzQ1jWoY_R2sRTE2g	0	2026-10-25 01:40:02.169401+00
8	cc018d28-8d17-5e40-b42f-bdb79c40758c	boot-1	4	c1a155eb-bfff-41ac-954b-6314433a952b	6000	2026-10-25 01:38:37.627934+00	phone_server_anchor	300	f	\N	\N	\N	f	\N	no_contact	t	904229f7-6dee-5ce6-85cb-51227471b2f4	boot-1	4	W_eUon_Ot2Y_K3xYzQ1jWoY_R2sRTE2g	0	2026-10-25 01:40:02.191789+00
9	904229f7-6dee-5ce6-85cb-51227471b2f4	boot-2	5	c1a155eb-bfff-41ac-954b-6314433a952b	8000	2026-10-25 01:38:39.627934+00	phone_server_anchor	300	f	\N	\N	\N	f	\N	no_contact	t	cc018d28-8d17-5e40-b42f-bdb79c40758c	boot-2	5	W_eUon_Ot2Y_K3xYzQ1jWoY_R2sRTE2g	0	2026-10-25 01:40:02.215204+00
10	cc018d28-8d17-5e40-b42f-bdb79c40758c	boot-1	5	c1a155eb-bfff-41ac-954b-6314433a952b	8000	2026-10-25 01:38:39.627934+00	phone_server_anchor	300	f	\N	\N	\N	f	\N	no_contact	t	904229f7-6dee-5ce6-85cb-51227471b2f4	boot-1	5	W_eUon_Ot2Y_K3xYzQ1jWoY_R2sRTE2g	0	2026-10-25 01:40:02.238015+00
11	904229f7-6dee-5ce6-85cb-51227471b2f4	boot-2	6	c1a155eb-bfff-41ac-954b-6314433a952b	10000	2026-10-25 01:38:41.627934+00	phone_server_anchor	300	f	\N	\N	\N	f	\N	no_contact	t	cc018d28-8d17-5e40-b42f-bdb79c40758c	boot-2	6	W_eUon_Ot2Y_K3xYzQ1jWoY_R2sRTE2g	0	2026-10-25 01:40:02.261617+00
12	cc018d28-8d17-5e40-b42f-bdb79c40758c	boot-1	6	c1a155eb-bfff-41ac-954b-6314433a952b	10000	2026-10-25 01:38:41.627934+00	phone_server_anchor	300	f	\N	\N	\N	f	\N	no_contact	t	904229f7-6dee-5ce6-85cb-51227471b2f4	boot-1	6	W_eUon_Ot2Y_K3xYzQ1jWoY_R2sRTE2g	0	2026-10-25 01:40:02.28412+00
13	904229f7-6dee-5ce6-85cb-51227471b2f4	boot-2	7	c1a155eb-bfff-41ac-954b-6314433a952b	12000	2026-10-25 01:38:43.627934+00	phone_server_anchor	300	f	\N	\N	\N	f	\N	no_contact	t	cc018d28-8d17-5e40-b42f-bdb79c40758c	boot-2	7	W_eUon_Ot2Y_K3xYzQ1jWoY_R2sRTE2g	0	2026-10-25 01:40:02.307436+00
14	cc018d28-8d17-5e40-b42f-bdb79c40758c	boot-1	7	c1a155eb-bfff-41ac-954b-6314433a952b	12000	2026-10-25 01:38:43.627934+00	phone_server_anchor	300	f	\N	\N	\N	f	\N	no_contact	t	904229f7-6dee-5ce6-85cb-51227471b2f4	boot-1	7	W_eUon_Ot2Y_K3xYzQ1jWoY_R2sRTE2g	0	2026-10-25 01:40:02.330092+00
15	904229f7-6dee-5ce6-85cb-51227471b2f4	boot-2	8	c1a155eb-bfff-41ac-954b-6314433a952b	14000	2026-10-25 01:38:45.627934+00	phone_server_anchor	300	f	\N	\N	\N	f	\N	no_contact	t	cc018d28-8d17-5e40-b42f-bdb79c40758c	boot-2	8	W_eUon_Ot2Y_K3xYzQ1jWoY_R2sRTE2g	0	2026-10-25 01:40:02.353033+00
16	cc018d28-8d17-5e40-b42f-bdb79c40758c	boot-1	8	c1a155eb-bfff-41ac-954b-6314433a952b	14000	2026-10-25 01:38:45.627934+00	phone_server_anchor	300	f	\N	\N	\N	f	\N	no_contact	t	904229f7-6dee-5ce6-85cb-51227471b2f4	boot-1	8	W_eUon_Ot2Y_K3xYzQ1jWoY_R2sRTE2g	0	2026-10-25 01:40:02.375511+00
17	904229f7-6dee-5ce6-85cb-51227471b2f4	boot-2	9	c1a155eb-bfff-41ac-954b-6314433a952b	16000	2026-10-25 01:38:47.627934+00	phone_server_anchor	300	f	\N	\N	\N	f	\N	no_contact	t	cc018d28-8d17-5e40-b42f-bdb79c40758c	boot-2	9	W_eUon_Ot2Y_K3xYzQ1jWoY_R2sRTE2g	0	2026-10-25 01:40:02.399044+00
18	cc018d28-8d17-5e40-b42f-bdb79c40758c	boot-1	9	c1a155eb-bfff-41ac-954b-6314433a952b	16000	2026-10-25 01:38:47.627934+00	phone_server_anchor	300	f	\N	\N	\N	f	\N	no_contact	t	904229f7-6dee-5ce6-85cb-51227471b2f4	boot-1	9	W_eUon_Ot2Y_K3xYzQ1jWoY_R2sRTE2g	0	2026-10-25 01:40:02.421233+00
19	904229f7-6dee-5ce6-85cb-51227471b2f4	boot-2	10	c1a155eb-bfff-41ac-954b-6314433a952b	18000	2026-10-25 01:38:49.627934+00	phone_server_anchor	300	f	\N	\N	\N	f	\N	no_contact	t	cc018d28-8d17-5e40-b42f-bdb79c40758c	boot-2	10	W_eUon_Ot2Y_K3xYzQ1jWoY_R2sRTE2g	0	2026-10-25 01:40:02.444273+00
20	cc018d28-8d17-5e40-b42f-bdb79c40758c	boot-1	10	c1a155eb-bfff-41ac-954b-6314433a952b	18000	2026-10-25 01:38:49.627934+00	phone_server_anchor	300	f	\N	\N	\N	f	\N	no_contact	t	904229f7-6dee-5ce6-85cb-51227471b2f4	boot-1	10	W_eUon_Ot2Y_K3xYzQ1jWoY_R2sRTE2g	0	2026-10-25 01:40:02.467319+00
21	904229f7-6dee-5ce6-85cb-51227471b2f4	boot-2	11	c1a155eb-bfff-41ac-954b-6314433a952b	20000	2026-10-25 01:38:51.627934+00	phone_server_anchor	300	f	\N	\N	\N	f	\N	no_contact	t	cc018d28-8d17-5e40-b42f-bdb79c40758c	boot-2	11	W_eUon_Ot2Y_K3xYzQ1jWoY_R2sRTE2g	0	2026-10-25 01:40:02.490598+00
22	cc018d28-8d17-5e40-b42f-bdb79c40758c	boot-1	11	c1a155eb-bfff-41ac-954b-6314433a952b	20000	2026-10-25 01:38:51.627934+00	phone_server_anchor	300	f	\N	\N	\N	f	\N	no_contact	t	904229f7-6dee-5ce6-85cb-51227471b2f4	boot-1	11	W_eUon_Ot2Y_K3xYzQ1jWoY_R2sRTE2g	0	2026-10-25 01:40:02.513014+00
23	904229f7-6dee-5ce6-85cb-51227471b2f4	boot-2	12	c1a155eb-bfff-41ac-954b-6314433a952b	22000	2026-10-25 01:38:53.627934+00	phone_server_anchor	300	f	\N	\N	\N	f	\N	no_contact	t	cc018d28-8d17-5e40-b42f-bdb79c40758c	boot-2	12	W_eUon_Ot2Y_K3xYzQ1jWoY_R2sRTE2g	0	2026-10-25 01:40:02.53617+00
24	cc018d28-8d17-5e40-b42f-bdb79c40758c	boot-1	12	c1a155eb-bfff-41ac-954b-6314433a952b	22000	2026-10-25 01:38:53.627934+00	phone_server_anchor	300	f	\N	\N	\N	f	\N	no_contact	t	904229f7-6dee-5ce6-85cb-51227471b2f4	boot-1	12	W_eUon_Ot2Y_K3xYzQ1jWoY_R2sRTE2g	0	2026-10-25 01:40:02.55865+00
25	904229f7-6dee-5ce6-85cb-51227471b2f4	boot-2	13	c1a155eb-bfff-41ac-954b-6314433a952b	24000	2026-10-25 01:38:55.627934+00	phone_server_anchor	300	f	\N	\N	\N	f	\N	no_contact	t	cc018d28-8d17-5e40-b42f-bdb79c40758c	boot-2	13	W_eUon_Ot2Y_K3xYzQ1jWoY_R2sRTE2g	0	2026-10-25 01:40:02.581831+00
26	cc018d28-8d17-5e40-b42f-bdb79c40758c	boot-1	13	c1a155eb-bfff-41ac-954b-6314433a952b	24000	2026-10-25 01:38:55.627934+00	phone_server_anchor	300	f	\N	\N	\N	f	\N	no_contact	t	904229f7-6dee-5ce6-85cb-51227471b2f4	boot-1	13	W_eUon_Ot2Y_K3xYzQ1jWoY_R2sRTE2g	0	2026-10-25 01:40:02.604495+00
27	904229f7-6dee-5ce6-85cb-51227471b2f4	boot-2	14	c1a155eb-bfff-41ac-954b-6314433a952b	26000	2026-10-25 01:38:57.627934+00	phone_server_anchor	300	f	\N	\N	\N	f	\N	no_contact	t	cc018d28-8d17-5e40-b42f-bdb79c40758c	boot-2	14	W_eUon_Ot2Y_K3xYzQ1jWoY_R2sRTE2g	0	2026-10-25 01:40:02.627629+00
28	cc018d28-8d17-5e40-b42f-bdb79c40758c	boot-1	14	c1a155eb-bfff-41ac-954b-6314433a952b	26000	2026-10-25 01:38:57.627934+00	phone_server_anchor	300	f	\N	\N	\N	f	\N	no_contact	t	904229f7-6dee-5ce6-85cb-51227471b2f4	boot-1	14	W_eUon_Ot2Y_K3xYzQ1jWoY_R2sRTE2g	0	2026-10-25 01:40:02.650357+00
29	904229f7-6dee-5ce6-85cb-51227471b2f4	boot-2	15	c1a155eb-bfff-41ac-954b-6314433a952b	28000	2026-10-25 01:38:59.627934+00	phone_server_anchor	300	f	\N	\N	\N	f	\N	no_contact	t	cc018d28-8d17-5e40-b42f-bdb79c40758c	boot-2	15	W_eUon_Ot2Y_K3xYzQ1jWoY_R2sRTE2g	0	2026-10-25 01:40:02.67398+00
30	cc018d28-8d17-5e40-b42f-bdb79c40758c	boot-1	15	c1a155eb-bfff-41ac-954b-6314433a952b	28000	2026-10-25 01:38:59.627934+00	phone_server_anchor	300	f	\N	\N	\N	f	\N	no_contact	t	904229f7-6dee-5ce6-85cb-51227471b2f4	boot-1	15	W_eUon_Ot2Y_K3xYzQ1jWoY_R2sRTE2g	0	2026-10-25 01:40:02.696343+00
31	904229f7-6dee-5ce6-85cb-51227471b2f4	boot-2	16	c1a155eb-bfff-41ac-954b-6314433a952b	30000	2026-10-25 01:39:01.627934+00	phone_server_anchor	300	f	\N	\N	\N	f	\N	no_contact	t	cc018d28-8d17-5e40-b42f-bdb79c40758c	boot-2	16	W_eUon_Ot2Y_K3xYzQ1jWoY_R2sRTE2g	0	2026-10-25 01:40:02.719623+00
32	cc018d28-8d17-5e40-b42f-bdb79c40758c	boot-1	16	c1a155eb-bfff-41ac-954b-6314433a952b	30000	2026-10-25 01:39:01.627934+00	phone_server_anchor	300	f	\N	\N	\N	f	\N	no_contact	t	904229f7-6dee-5ce6-85cb-51227471b2f4	boot-1	16	W_eUon_Ot2Y_K3xYzQ1jWoY_R2sRTE2g	0	2026-10-25 01:40:02.742615+00
33	904229f7-6dee-5ce6-85cb-51227471b2f4	emulator-fixture-boot1	1	\N	1000	2026-10-25 12:30:01.946549+00	phone_server_anchor	500	f	\N	\N	\N	t	73	valid	f	\N	\N	\N	\N	\N	2026-10-25 12:30:51.192637+00
34	904229f7-6dee-5ce6-85cb-51227471b2f4	emulator-fixture-boot1	2	\N	2000	2026-10-25 12:30:02.018887+00	phone_server_anchor	500	f	\N	\N	\N	t	74	valid	f	\N	\N	\N	\N	\N	2026-10-25 12:30:51.192637+00
35	904229f7-6dee-5ce6-85cb-51227471b2f4	emulator-fixture-boot1	3	\N	3000	2026-10-25 12:30:02.026289+00	phone_server_anchor	500	f	\N	\N	\N	t	75	valid	f	\N	\N	\N	\N	\N	2026-10-25 12:30:51.192637+00
36	904229f7-6dee-5ce6-85cb-51227471b2f4	emulator-fixture-boot1	4	\N	4000	2026-10-25 12:30:02.02815+00	phone_server_anchor	500	f	\N	\N	\N	t	76	valid	f	\N	\N	\N	\N	\N	2026-10-25 12:30:51.192637+00
37	904229f7-6dee-5ce6-85cb-51227471b2f4	emulator-fixture-boot1	5	\N	5000	2026-10-25 12:30:02.036704+00	phone_server_anchor	500	f	\N	\N	\N	t	77	valid	f	\N	\N	\N	\N	\N	2026-10-25 12:30:51.192637+00
38	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	3	\N	4461	\N	unsynced	\N	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:28:00.239411+00
39	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	4	\N	5467	\N	unsynced	\N	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:28:02.369902+00
40	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	5	\N	6470	\N	unsynced	\N	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:28:02.369902+00
41	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	6	\N	7471	2026-10-25 18:28:01+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:28:04.475551+00
42	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	12	\N	13489	2026-10-25 18:28:08+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:28:10.55644+00
43	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	13	\N	14492	2026-10-25 18:28:09+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:28:10.55644+00
44	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	14	\N	15496	2026-10-25 18:28:10+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:28:12.664442+00
45	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	15	\N	16502	2026-10-25 18:28:11+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:28:12.664442+00
46	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	21	\N	22527	2026-10-25 18:28:17+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:28:18.748424+00
47	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	22	\N	23532	2026-10-25 18:28:17+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:28:20.878784+00
48	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	23	\N	24535	2026-10-25 18:28:18+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:28:20.878784+00
49	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	27	\N	28546	2026-10-25 18:28:22+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:28:25.044207+00
50	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	28	\N	29551	2026-10-25 18:28:24+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:28:25.044207+00
51	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	29	\N	30556	2026-10-25 18:28:25+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:28:27.184095+00
52	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	30	\N	31558	2026-10-25 18:28:26+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:28:27.184095+00
53	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	37	\N	38585	2026-10-25 18:28:33+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:28:35.351268+00
54	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	38	\N	39593	2026-10-25 18:28:33+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:28:35.351268+00
55	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	39	\N	40598	2026-10-25 18:28:34+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:28:37.446654+00
56	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	40	\N	41601	2026-10-25 18:28:35+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:28:37.446654+00
57	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	49	\N	50644	2026-10-25 18:28:45+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:28:47.565141+00
58	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	50	\N	51645	2026-10-25 18:28:46+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:28:47.565141+00
59	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	51	\N	52654	2026-10-25 18:28:47+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:28:49.684046+00
60	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	52	\N	53656	2026-10-25 18:28:48+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:28:49.684046+00
61	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	56	\N	57677	2026-10-25 18:28:52+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:28:53.79463+00
62	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	57	\N	58682	2026-10-25 18:28:53+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:28:55.927077+00
63	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	58	\N	59686	2026-10-25 18:28:54+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:28:55.927077+00
64	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	64	\N	65711	2026-10-25 18:29:00+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:29:02.022782+00
65	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	65	\N	66717	2026-10-25 18:29:01+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:29:02.022782+00
66	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	66	\N	67716	2026-10-25 18:29:02+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:29:04.165785+00
67	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	67	\N	68724	2026-10-25 18:29:03+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:29:04.165785+00
68	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	70	\N	71737	2026-10-25 18:29:06+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:29:08.318538+00
69	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	71	\N	72737	2026-10-25 18:29:07+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:29:08.318538+00
70	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	72	\N	73742	2026-10-25 18:29:08+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:29:10.417967+00
71	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	73	\N	74750	2026-10-25 18:29:09+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:29:10.417967+00
72	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	79	\N	80837	2026-10-25 18:29:15+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:29:16.497821+00
73	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	80	\N	81842	2026-10-25 18:29:16+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:29:18.62378+00
74	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	81	\N	82842	2026-10-25 18:29:17+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:29:18.62378+00
75	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	82	\N	83846	2026-10-25 18:29:18+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:29:20.744+00
76	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	92	\N	94048	2026-10-25 18:29:28+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:29:30.863376+00
77	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	93	\N	95051	2026-10-25 18:29:29+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:29:30.863376+00
78	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	94	\N	96058	2026-10-25 18:29:30+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:29:32.986023+00
79	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	95	\N	97067	2026-10-25 18:29:31+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:29:32.986023+00
80	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	102	\N	104098	2026-10-25 18:29:38+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:29:41.087294+00
81	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	103	\N	105103	2026-10-25 18:29:40+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:29:41.087294+00
82	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	104	\N	106107	2026-10-25 18:29:41+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:29:43.200983+00
83	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	105	\N	107107	2026-10-25 18:29:42+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:29:43.200983+00
84	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	111	\N	113142	2026-10-25 18:29:48+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:29:49.329016+00
85	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	112	\N	114145	2026-10-25 18:29:49+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:29:51.583441+00
86	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	113	\N	115150	2026-10-25 18:29:49+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:29:51.583441+00
87	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	114	\N	116154	2026-10-25 18:29:50+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:29:51.583441+00
88	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	117	\N	119172	2026-10-25 18:29:53+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:29:55.752924+00
89	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	118	\N	120176	2026-10-25 18:29:54+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:29:55.752924+00
90	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	119	\N	121183	2026-10-25 18:29:55+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:29:57.965233+00
91	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	120	\N	122192	2026-10-25 18:29:56+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:29:57.965233+00
92	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	130	\N	132238	2026-10-25 18:30:06+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:30:08.066076+00
93	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	131	\N	133241	2026-10-25 18:30:07+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:30:10.175366+00
94	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	132	\N	134246	2026-10-25 18:30:08+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:30:10.175366+00
95	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	133	\N	135249	2026-10-25 18:30:09+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:30:12.297161+00
96	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	139	\N	141269	2026-10-25 18:30:15+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:30:18.401455+00
97	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	140	\N	142269	2026-10-25 18:30:16+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:30:18.401455+00
98	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	141	\N	143270	2026-10-25 18:30:17+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:30:20.494461+00
99	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	142	\N	144273	2026-10-25 18:30:18+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:30:20.494461+00
100	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	148	\N	150287	2026-10-25 18:30:24+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:30:26.563689+00
101	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	149	\N	151291	2026-10-25 18:30:25+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:30:26.563689+00
102	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	150	\N	152293	2026-10-25 18:30:27+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:30:28.68749+00
103	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	151	\N	153296	2026-10-25 18:30:28+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:30:28.68749+00
104	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	155	\N	157317	2026-10-25 18:30:32+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:30:32.824141+00
108	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	167	\N	169369	2026-10-25 18:30:43+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:30:45.416578+00
105	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	156	\N	158322	2026-10-25 18:30:33+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:30:34.966499+00
106	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	157	\N	159327	2026-10-25 18:30:33+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:30:34.966499+00
107	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	158	\N	160329	2026-10-25 18:30:34+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:30:37.143118+00
109	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	168	\N	170372	2026-10-25 18:30:44+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:30:47.566178+00
110	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	169	\N	171377	2026-10-25 18:30:46+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:30:47.566178+00
111	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	170	\N	172377	2026-10-25 18:30:47+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:30:49.684453+00
112	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	180	\N	182415	2026-10-25 18:30:57+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:30:57.801291+00
113	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	181	\N	183418	2026-10-25 18:30:58+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:31:00.033401+00
114	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	182	\N	184422	2026-10-25 18:30:58+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:31:00.033401+00
115	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	189	\N	191448	2026-10-25 18:31:05+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:31:08.24944+00
116	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	190	\N	192457	2026-10-25 18:31:06+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:31:08.24944+00
117	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	191	\N	193462	2026-10-25 18:31:07+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:31:10.357933+00
118	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	192	\N	194465	2026-10-25 18:31:08+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:31:10.357933+00
119	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	194	\N	196471	2026-10-25 18:31:10+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:31:12.611635+00
120	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	195	\N	197471	2026-10-25 18:31:11+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:31:14.781203+00
121	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	196	\N	198474	2026-10-25 18:31:12+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:31:14.781203+00
122	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	197	\N	199478	2026-10-25 18:31:14+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:31:14.781203+00
123	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	204	\N	206526	2026-10-25 18:31:21+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:31:23.011602+00
124	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	205	\N	207526	2026-10-25 18:31:22+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:31:23.011602+00
125	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	206	\N	208530	2026-10-25 18:31:23+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:31:25.148252+00
126	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	207	\N	209536	2026-10-25 18:31:23+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:31:25.148252+00
127	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	346	\N	349199	2026-10-25 18:33:43+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:33:45.83691+00
128	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	347	\N	350203	2026-10-25 18:33:45+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:33:45.83691+00
129	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	348	\N	351207	2026-10-25 18:33:46+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:33:47.915498+00
130	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	349	\N	352211	2026-10-25 18:33:47+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:33:47.915498+00
131	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	352	\N	355220	2026-10-25 18:33:50+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:33:51.980375+00
132	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	353	\N	356221	2026-10-25 18:33:51+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:33:51.980375+00
133	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	354	\N	357227	2026-10-25 18:33:51+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:33:54.081772+00
134	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	361	\N	364253	2026-10-25 18:33:58+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:34:00.135846+00
135	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	362	\N	365257	2026-10-25 18:33:59+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:34:02.256572+00
136	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	363	\N	366257	2026-10-25 18:34:00+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:34:02.256572+00
137	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	364	\N	367259	2026-10-25 18:34:01+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:34:04.352895+00
138	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	370	\N	373284	2026-10-25 18:34:07+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:34:08.425488+00
139	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	371	\N	374287	2026-10-25 18:34:08+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:34:10.546791+00
140	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	372	\N	375291	2026-10-25 18:34:10+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:34:10.546791+00
141	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	373	\N	376293	2026-10-25 18:34:11+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:34:12.685052+00
142	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	376	\N	379303	2026-10-25 18:34:14+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:34:14.755323+00
143	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	377	\N	380306	2026-10-25 18:34:15+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:34:16.883636+00
144	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	378	\N	381308	2026-10-25 18:34:16+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:34:16.883636+00
145	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	379	\N	382316	2026-10-25 18:34:16+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:34:19.02378+00
146	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	380	\N	383319	2026-10-25 18:34:17+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:34:19.02378+00
147	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	386	\N	389349	2026-10-25 18:34:23+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:34:25.106311+00
148	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	387	\N	390352	2026-10-25 18:34:24+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:34:27.247158+00
149	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	388	\N	391354	2026-10-25 18:34:25+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:34:27.247158+00
150	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	389	\N	392357	2026-10-25 18:34:26+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:34:29.366923+00
151	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	395	\N	398382	2026-10-25 18:34:32+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:34:33.44127+00
152	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	396	\N	399385	2026-10-25 18:34:33+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:34:35.555858+00
153	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	397	\N	400389	2026-10-25 18:34:34+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:34:35.555858+00
154	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	398	\N	401390	2026-10-25 18:34:35+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:34:37.687736+00
155	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	401	\N	404407	2026-10-25 18:34:38+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:34:39.737381+00
156	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	402	\N	405411	2026-10-25 18:34:39+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:34:41.848589+00
157	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	403	\N	406412	2026-10-25 18:34:40+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:34:41.848589+00
158	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	404	\N	407418	2026-10-25 18:34:41+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:34:43.996344+00
159	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	405	\N	408421	2026-10-25 18:34:42+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:34:43.996344+00
160	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	417	\N	420483	2026-10-25 18:34:54+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:34:56.118558+00
161	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	418	\N	421484	2026-10-25 18:34:55+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:34:58.246765+00
162	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	419	\N	422488	2026-10-25 18:34:57+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:34:58.246765+00
163	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	420	\N	423492	2026-10-25 18:34:58+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:35:00.386236+00
164	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	426	\N	429514	2026-10-25 18:35:04+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:35:06.496315+00
165	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	427	\N	430517	2026-10-25 18:35:05+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:35:06.496315+00
166	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	428	\N	431518	2026-10-25 18:35:06+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:35:08.694235+00
167	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	429	\N	432522	2026-10-25 18:35:06+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:35:08.694235+00
168	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	430	\N	433525	2026-10-25 18:35:07+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:35:08.694235+00
169	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	436	\N	439548	2026-10-25 18:35:13+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:35:14.773164+00
175	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	447	\N	450937	2026-10-25 18:35:25+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:35:27.211254+00
176	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	448	\N	451941	2026-10-25 18:35:26+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:35:27.211254+00
178	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	454	\N	457962	2026-10-25 18:35:32+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:35:33.412907+00
188	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	471	\N	475022	2026-10-25 18:35:49+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:35:52.085724+00
189	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	472	\N	476030	2026-10-25 18:35:50+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:35:52.085724+00
190	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	473	\N	477033	2026-10-25 18:35:51+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:35:52.085724+00
170	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	437	\N	440555	2026-10-25 18:35:14+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:35:16.883454+00
171	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	438	\N	441556	2026-10-25 18:35:16+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:35:16.883454+00
172	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	439	\N	442558	2026-10-25 18:35:17+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:35:18.99345+00
173	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	440	\N	443560	2026-10-25 18:35:18+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:35:18.99345+00
174	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	446	\N	449596	2026-10-25 18:35:24+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:35:25.068659+00
177	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	449	\N	452945	2026-10-25 18:35:27+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:35:29.333086+00
179	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	455	\N	458966	2026-10-25 18:35:33+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:35:35.542226+00
180	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	456	\N	459970	2026-10-25 18:35:34+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:35:35.542226+00
181	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	457	\N	460972	2026-10-25 18:35:34+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:35:37.655289+00
182	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	458	\N	461977	2026-10-25 18:35:35+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:35:37.655289+00
183	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	461	\N	464985	2026-10-25 18:35:38+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:35:41.755021+00
184	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	462	\N	465986	2026-10-25 18:35:39+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:35:41.755021+00
185	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	463	\N	466991	2026-10-25 18:35:41+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:35:43.896209+00
186	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	464	\N	467995	2026-10-25 18:35:42+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:35:43.896209+00
187	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	470	\N	474018	2026-10-25 18:35:48+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:35:49.975809+00
191	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	476	\N	480042	2026-10-25 18:35:54+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:35:56.287753+00
192	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	477	\N	481042	2026-10-25 18:35:55+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:35:56.287753+00
193	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	478	\N	482046	2026-10-25 18:35:56+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:35:58.386657+00
194	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	479	\N	483050	2026-10-25 18:35:57+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:35:58.386657+00
195	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	488	\N	492101	2026-10-25 18:36:06+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:36:08.561849+00
196	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	489	\N	493105	2026-10-25 18:36:07+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:36:08.561849+00
197	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	490	\N	494108	2026-10-25 18:36:08+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:36:10.678584+00
198	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	491	\N	495113	2026-10-25 18:36:09+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:36:10.678584+00
199	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	492	\N	496115	2026-10-25 18:36:10+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:36:12.803409+00
200	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	498	\N	502134	2026-10-25 18:36:16+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:36:18.883382+00
201	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	499	\N	503136	2026-10-25 18:36:17+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:36:18.883382+00
202	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	500	\N	504141	2026-10-25 18:36:18+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:36:21.020853+00
203	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	501	\N	505144	2026-10-25 18:36:19+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:36:21.020853+00
204	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	503	\N	507156	2026-10-25 18:36:21+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:36:23.101269+00
205	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	504	\N	508160	2026-10-25 18:36:22+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:36:25.239399+00
206	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	505	\N	509165	2026-10-25 18:36:23+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:36:25.239399+00
207	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	506	\N	510168	2026-10-25 18:36:24+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:36:25.239399+00
208	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	507	\N	511173	2026-10-25 18:36:25+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:36:27.410869+00
209	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	513	\N	517189	2026-10-25 18:36:31+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:36:33.502561+00
210	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	514	\N	518192	2026-10-25 18:36:32+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:36:33.502561+00
211	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	515	\N	519197	2026-10-25 18:36:33+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-25 18:36:35.64033+00
212	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	62	30f11f19-c0bf-4c64-a167-6a0ec697e18b	74766	2026-10-26 04:36:34+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:36:37.066999+00
213	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	63	30f11f19-c0bf-4c64-a167-6a0ec697e18b	75771	2026-10-26 04:36:34+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:36:37.066999+00
214	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	74	30f11f19-c0bf-4c64-a167-6a0ec697e18b	86848	2026-10-26 04:36:45+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:36:47.27315+00
215	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	75	30f11f19-c0bf-4c64-a167-6a0ec697e18b	87856	2026-10-26 04:36:47+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:36:49.45921+00
216	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	76	30f11f19-c0bf-4c64-a167-6a0ec697e18b	88863	2026-10-26 04:36:48+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:36:49.45921+00
217	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	77	30f11f19-c0bf-4c64-a167-6a0ec697e18b	89870	2026-10-26 04:36:49+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:36:51.587644+00
218	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	88	30f11f19-c0bf-4c64-a167-6a0ec697e18b	100948	2026-10-26 04:37:00+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:37:01.711201+00
219	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	89	30f11f19-c0bf-4c64-a167-6a0ec697e18b	101955	2026-10-26 04:37:01+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:37:03.826122+00
220	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	90	30f11f19-c0bf-4c64-a167-6a0ec697e18b	102963	2026-10-26 04:37:02+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:37:03.826122+00
221	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	96	30f11f19-c0bf-4c64-a167-6a0ec697e18b	109004	2026-10-26 04:37:08+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:37:10.072343+00
222	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	97	30f11f19-c0bf-4c64-a167-6a0ec697e18b	110011	2026-10-26 04:37:09+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:37:12.177673+00
223	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	107	30f11f19-c0bf-4c64-a167-6a0ec697e18b	120082	2026-10-26 04:37:19+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:37:20.254934+00
224	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	108	30f11f19-c0bf-4c64-a167-6a0ec697e18b	121090	2026-10-26 04:37:20+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:37:22.359572+00
225	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	109	30f11f19-c0bf-4c64-a167-6a0ec697e18b	122097	2026-10-26 04:37:21+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:37:22.359572+00
226	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	110	30f11f19-c0bf-4c64-a167-6a0ec697e18b	123104	2026-10-26 04:37:22+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:37:24.552111+00
227	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	115	30f11f19-c0bf-4c64-a167-6a0ec697e18b	128142	2026-10-26 04:37:27+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:37:28.634846+00
228	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	116	30f11f19-c0bf-4c64-a167-6a0ec697e18b	129151	2026-10-26 04:37:28+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:37:30.916765+00
229	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	124	30f11f19-c0bf-4c64-a167-6a0ec697e18b	137208	2026-10-26 04:37:36+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:37:39.022064+00
230	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	125	30f11f19-c0bf-4c64-a167-6a0ec697e18b	138215	2026-10-26 04:37:37+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:37:39.022064+00
231	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	126	30f11f19-c0bf-4c64-a167-6a0ec697e18b	139222	2026-10-26 04:37:38+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:37:41.170149+00
232	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	127	30f11f19-c0bf-4c64-a167-6a0ec697e18b	140230	2026-10-26 04:37:39+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:37:41.170149+00
233	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	134	30f11f19-c0bf-4c64-a167-6a0ec697e18b	147277	2026-10-26 04:37:46+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:37:49.435092+00
234	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	135	30f11f19-c0bf-4c64-a167-6a0ec697e18b	148284	2026-10-26 04:37:47+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:37:49.435092+00
240	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	153	30f11f19-c0bf-4c64-a167-6a0ec697e18b	166511	2026-10-26 04:38:06+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:38:07.854487+00
241	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	154	30f11f19-c0bf-4c64-a167-6a0ec697e18b	167519	2026-10-26 04:38:06+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:38:07.854487+00
243	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	176	30f11f19-c0bf-4c64-a167-6a0ec697e18b	189675	2026-10-26 04:38:29+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:38:30.494299+00
249	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	187	30f11f19-c0bf-4c64-a167-6a0ec697e18b	200753	2026-10-26 04:38:39+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:38:43.054868+00
250	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	188	30f11f19-c0bf-4c64-a167-6a0ec697e18b	201761	2026-10-26 04:38:40+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:38:43.054868+00
251	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	193	30f11f19-c0bf-4c64-a167-6a0ec697e18b	206796	2026-10-26 04:38:46+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:38:47.244928+00
252	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	201	30f11f19-c0bf-4c64-a167-6a0ec697e18b	214853	2026-10-26 04:38:54+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:38:55.477684+00
253	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	202	30f11f19-c0bf-4c64-a167-6a0ec697e18b	215859	2026-10-26 04:38:54+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:38:57.611488+00
254	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	203	30f11f19-c0bf-4c64-a167-6a0ec697e18b	216867	2026-10-26 04:38:55+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:38:57.611488+00
255	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	211	30f11f19-c0bf-4c64-a167-6a0ec697e18b	224923	2026-10-26 04:39:03+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:39:05.834061+00
261	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	223	30f11f19-c0bf-4c64-a167-6a0ec697e18b	237006	2026-10-26 04:39:16+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:39:18.251549+00
262	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	224	30f11f19-c0bf-4c64-a167-6a0ec697e18b	238014	2026-10-26 04:39:16+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:39:18.251549+00
235	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	136	30f11f19-c0bf-4c64-a167-6a0ec697e18b	149291	2026-10-26 04:37:48+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:37:51.552241+00
236	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	143	30f11f19-c0bf-4c64-a167-6a0ec697e18b	156342	2026-10-26 04:37:55+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:37:57.63509+00
237	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	144	30f11f19-c0bf-4c64-a167-6a0ec697e18b	157349	2026-10-26 04:37:57+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:37:57.63509+00
238	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	145	30f11f19-c0bf-4c64-a167-6a0ec697e18b	158355	2026-10-26 04:37:58+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:37:59.736046+00
239	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	146	30f11f19-c0bf-4c64-a167-6a0ec697e18b	159363	2026-10-26 04:37:59+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:37:59.736046+00
242	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	166	30f11f19-c0bf-4c64-a167-6a0ec697e18b	179603	2026-10-26 04:38:19+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:38:20.146976+00
244	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	177	30f11f19-c0bf-4c64-a167-6a0ec697e18b	190683	2026-10-26 04:38:30+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:38:32.609733+00
245	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	178	30f11f19-c0bf-4c64-a167-6a0ec697e18b	191689	2026-10-26 04:38:31+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:38:32.609733+00
246	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	179	30f11f19-c0bf-4c64-a167-6a0ec697e18b	192696	2026-10-26 04:38:32+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:38:34.717048+00
247	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	185	30f11f19-c0bf-4c64-a167-6a0ec697e18b	198739	2026-10-26 04:38:38+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:38:38.786622+00
248	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	186	30f11f19-c0bf-4c64-a167-6a0ec697e18b	199746	2026-10-26 04:38:38+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:38:40.920124+00
256	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	212	30f11f19-c0bf-4c64-a167-6a0ec697e18b	225930	2026-10-26 04:39:04+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:39:07.970521+00
257	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	213	30f11f19-c0bf-4c64-a167-6a0ec697e18b	226937	2026-10-26 04:39:05+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:39:07.970521+00
258	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	214	30f11f19-c0bf-4c64-a167-6a0ec697e18b	227945	2026-10-26 04:39:07+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:39:10.088231+00
259	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	221	30f11f19-c0bf-4c64-a167-6a0ec697e18b	234992	2026-10-26 04:39:14+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:39:16.153389+00
260	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	222	30f11f19-c0bf-4c64-a167-6a0ec697e18b	235999	2026-10-26 04:39:15+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:39:16.153389+00
263	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	230	30f11f19-c0bf-4c64-a167-6a0ec697e18b	244055	2026-10-26 04:39:22+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:39:24.334417+00
264	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	231	30f11f19-c0bf-4c64-a167-6a0ec697e18b	245062	2026-10-26 04:39:23+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:39:26.445774+00
265	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	232	30f11f19-c0bf-4c64-a167-6a0ec697e18b	246070	2026-10-26 04:39:24+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:39:26.445774+00
266	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	233	30f11f19-c0bf-4c64-a167-6a0ec697e18b	247077	2026-10-26 04:39:26+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:39:28.565274+00
267	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	243	30f11f19-c0bf-4c64-a167-6a0ec697e18b	257148	2026-10-26 04:39:36+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:39:38.66652+00
268	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	244	30f11f19-c0bf-4c64-a167-6a0ec697e18b	258155	2026-10-26 04:39:37+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:39:38.66652+00
269	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	245	30f11f19-c0bf-4c64-a167-6a0ec697e18b	259162	2026-10-26 04:39:38+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:39:40.95645+00
270	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	246	30f11f19-c0bf-4c64-a167-6a0ec697e18b	260170	2026-10-26 04:39:39+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:39:40.95645+00
271	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	256	30f11f19-c0bf-4c64-a167-6a0ec697e18b	270242	2026-10-26 04:39:49+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:39:51.053816+00
272	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	257	30f11f19-c0bf-4c64-a167-6a0ec697e18b	271250	2026-10-26 04:39:50+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:39:53.171308+00
273	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	258	30f11f19-c0bf-4c64-a167-6a0ec697e18b	272256	2026-10-26 04:39:51+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:39:53.171308+00
274	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	259	30f11f19-c0bf-4c64-a167-6a0ec697e18b	273266	2026-10-26 04:39:52+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:39:55.297602+00
275	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	269	30f11f19-c0bf-4c64-a167-6a0ec697e18b	283337	2026-10-26 04:40:02+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:40:03.386015+00
276	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	270	30f11f19-c0bf-4c64-a167-6a0ec697e18b	284344	2026-10-26 04:40:03+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:40:05.522163+00
277	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	271	30f11f19-c0bf-4c64-a167-6a0ec697e18b	285351	2026-10-26 04:40:04+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:40:05.522163+00
278	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	272	30f11f19-c0bf-4c64-a167-6a0ec697e18b	286359	2026-10-26 04:40:05+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:40:07.663386+00
279	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	278	30f11f19-c0bf-4c64-a167-6a0ec697e18b	292399	2026-10-26 04:40:11+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:40:13.748631+00
280	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	279	30f11f19-c0bf-4c64-a167-6a0ec697e18b	293406	2026-10-26 04:40:12+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:40:13.748631+00
281	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	280	30f11f19-c0bf-4c64-a167-6a0ec697e18b	294415	2026-10-26 04:40:13+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:40:15.879312+00
282	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	281	30f11f19-c0bf-4c64-a167-6a0ec697e18b	295423	2026-10-26 04:40:14+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:40:15.879312+00
283	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	288	30f11f19-c0bf-4c64-a167-6a0ec697e18b	302491	2026-10-26 04:40:21+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:40:23.963846+00
284	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	289	30f11f19-c0bf-4c64-a167-6a0ec697e18b	303499	2026-10-26 04:40:22+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:40:23.963846+00
285	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	290	30f11f19-c0bf-4c64-a167-6a0ec697e18b	304507	2026-10-26 04:40:23+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:40:26.082075+00
286	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	293	30f11f19-c0bf-4c64-a167-6a0ec697e18b	307528	2026-10-26 04:40:26+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:40:28.164612+00
287	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	294	30f11f19-c0bf-4c64-a167-6a0ec697e18b	308535	2026-10-26 04:40:27+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:40:30.285926+00
288	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	295	30f11f19-c0bf-4c64-a167-6a0ec697e18b	309542	2026-10-26 04:40:29+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:40:30.285926+00
289	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	296	30f11f19-c0bf-4c64-a167-6a0ec697e18b	310553	2026-10-26 04:40:30+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:40:32.397142+00
290	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	303	30f11f19-c0bf-4c64-a167-6a0ec697e18b	317599	2026-10-26 04:40:37+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:40:38.477797+00
291	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	304	30f11f19-c0bf-4c64-a167-6a0ec697e18b	318607	2026-10-26 04:40:38+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:40:40.737439+00
292	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	305	30f11f19-c0bf-4c64-a167-6a0ec697e18b	319614	2026-10-26 04:40:38+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:40:40.737439+00
293	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	306	30f11f19-c0bf-4c64-a167-6a0ec697e18b	320622	2026-10-26 04:40:39+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:40:40.737439+00
294	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	312	30f11f19-c0bf-4c64-a167-6a0ec697e18b	326665	2026-10-26 04:40:45+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:40:46.828909+00
295	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	313	30f11f19-c0bf-4c64-a167-6a0ec697e18b	327670	2026-10-26 04:40:46+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:40:48.961723+00
296	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	314	30f11f19-c0bf-4c64-a167-6a0ec697e18b	328677	2026-10-26 04:40:48+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:40:48.961723+00
297	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	315	30f11f19-c0bf-4c64-a167-6a0ec697e18b	329685	2026-10-26 04:40:49+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:40:51.122378+00
298	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	318	30f11f19-c0bf-4c64-a167-6a0ec697e18b	332707	2026-10-26 04:40:52+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:40:53.211821+00
299	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	319	30f11f19-c0bf-4c64-a167-6a0ec697e18b	333715	2026-10-26 04:40:53+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:40:55.369905+00
300	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	320	30f11f19-c0bf-4c64-a167-6a0ec697e18b	334722	2026-10-26 04:40:54+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:40:55.369905+00
301	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	321	30f11f19-c0bf-4c64-a167-6a0ec697e18b	335728	2026-10-26 04:40:54+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:40:57.518244+00
302	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	328	30f11f19-c0bf-4c64-a167-6a0ec697e18b	342779	2026-10-26 04:41:01+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:41:03.615202+00
305	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	331	30f11f19-c0bf-4c64-a167-6a0ec697e18b	345802	2026-10-26 04:41:04+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:41:07.897275+00
307	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	344	30f11f19-c0bf-4c64-a167-6a0ec697e18b	358895	2026-10-26 04:41:17+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:41:20.132801+00
308	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	345	30f11f19-c0bf-4c64-a167-6a0ec697e18b	359902	2026-10-26 04:41:19+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:41:20.132801+00
309	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	355	30f11f19-c0bf-4c64-a167-6a0ec697e18b	369975	2026-10-26 04:41:29+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:41:30.408625+00
312	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	360	30f11f19-c0bf-4c64-a167-6a0ec697e18b	375010	2026-10-26 04:41:34+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:41:36.629157+00
313	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	381	30f11f19-c0bf-4c64-a167-6a0ec697e18b	396160	2026-10-26 04:41:54+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:41:56.93303+00
316	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	391	30f11f19-c0bf-4c64-a167-6a0ec697e18b	406229	2026-10-26 04:42:05+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:42:07.177224+00
317	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	392	30f11f19-c0bf-4c64-a167-6a0ec697e18b	407237	2026-10-26 04:42:06+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:42:07.177224+00
318	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	393	30f11f19-c0bf-4c64-a167-6a0ec697e18b	408244	2026-10-26 04:42:07+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:42:09.304337+00
319	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	394	30f11f19-c0bf-4c64-a167-6a0ec697e18b	409250	2026-10-26 04:42:08+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:42:09.304337+00
320	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	400	30f11f19-c0bf-4c64-a167-6a0ec697e18b	415293	2026-10-26 04:42:14+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:42:15.437721+00
321	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1008	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1028123	2026-10-26 04:52:27+00	phone_server_anchor	500	f	\N	\N	\N	t	88	valid	f	\N	\N	\N	\N	\N	2026-10-26 04:52:27.915735+00
326	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1019	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1039469	2026-10-26 04:52:38+00	phone_server_anchor	500	f	\N	\N	\N	t	72	valid	f	\N	\N	\N	\N	\N	2026-10-26 04:52:40.277838+00
327	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1020	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1040477	2026-10-26 04:52:39+00	phone_server_anchor	500	f	\N	\N	\N	t	94	valid	f	\N	\N	\N	\N	\N	2026-10-26 04:52:40.277838+00
330	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1031	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1051560	2026-10-26 04:52:50+00	phone_server_anchor	500	f	\N	\N	\N	t	59	valid	f	\N	\N	\N	\N	\N	2026-10-26 04:52:52.519139+00
331	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1032	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1052568	2026-10-26 04:52:50+00	phone_server_anchor	500	f	\N	\N	\N	t	59	valid	f	\N	\N	\N	\N	\N	2026-10-26 04:52:52.519139+00
336	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1044	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1064656	2026-10-26 04:53:03+00	phone_server_anchor	500	f	\N	\N	\N	t	57	valid	f	\N	\N	\N	\N	\N	2026-10-26 04:53:04.808779+00
343	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1056	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1076748	2026-10-26 04:53:14+00	phone_server_anchor	500	f	\N	\N	\N	t	110	valid	f	\N	\N	\N	\N	\N	2026-10-26 04:53:17.383019+00
344	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1057	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1077756	2026-10-26 04:53:16+00	phone_server_anchor	500	f	\N	\N	\N	t	70	valid	f	\N	\N	\N	\N	\N	2026-10-26 04:53:17.383019+00
303	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	329	30f11f19-c0bf-4c64-a167-6a0ec697e18b	343787	2026-10-26 04:41:03+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:41:05.758059+00
304	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	330	30f11f19-c0bf-4c64-a167-6a0ec697e18b	344795	2026-10-26 04:41:03+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:41:05.758059+00
306	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	343	30f11f19-c0bf-4c64-a167-6a0ec697e18b	357888	2026-10-26 04:41:16+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:41:17.997064+00
310	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	358	30f11f19-c0bf-4c64-a167-6a0ec697e18b	372996	2026-10-26 04:41:32+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:41:34.492407+00
311	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	359	30f11f19-c0bf-4c64-a167-6a0ec697e18b	374003	2026-10-26 04:41:33+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:41:34.492407+00
314	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	382	30f11f19-c0bf-4c64-a167-6a0ec697e18b	397167	2026-10-26 04:41:55+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:41:59.072617+00
315	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	383	30f11f19-c0bf-4c64-a167-6a0ec697e18b	398175	2026-10-26 04:41:57+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:41:59.072617+00
322	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1009	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1029130	2026-10-26 04:52:28+00	phone_server_anchor	500	f	\N	\N	\N	t	90	valid	f	\N	\N	\N	\N	\N	2026-10-26 04:52:30.007181+00
323	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1010	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1030138	2026-10-26 04:52:29+00	phone_server_anchor	500	f	\N	\N	\N	t	75	valid	f	\N	\N	\N	\N	\N	2026-10-26 04:52:30.007181+00
324	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1017	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1037453	2026-10-26 04:52:36+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	warming_up	f	\N	\N	\N	\N	\N	2026-10-26 04:52:38.157798+00
325	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1018	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1038461	2026-10-26 04:52:37+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	warming_up	f	\N	\N	\N	\N	\N	2026-10-26 04:52:38.157798+00
328	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1029	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1049546	2026-10-26 04:52:48+00	phone_server_anchor	500	f	\N	\N	\N	t	97	valid	f	\N	\N	\N	\N	\N	2026-10-26 04:52:50.394221+00
329	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1030	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1050553	2026-10-26 04:52:49+00	phone_server_anchor	500	f	\N	\N	\N	t	69	valid	f	\N	\N	\N	\N	\N	2026-10-26 04:52:50.394221+00
332	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1039	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1059622	2026-10-26 04:52:57+00	phone_server_anchor	500	f	\N	\N	\N	t	62	valid	f	\N	\N	\N	\N	\N	2026-10-26 04:53:00.601601+00
333	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1040	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1060628	2026-10-26 04:52:58+00	phone_server_anchor	500	f	\N	\N	\N	t	71	valid	f	\N	\N	\N	\N	\N	2026-10-26 04:53:00.601601+00
334	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1041	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1061634	2026-10-26 04:53:00+00	phone_server_anchor	500	f	\N	\N	\N	t	71	valid	f	\N	\N	\N	\N	\N	2026-10-26 04:53:02.729734+00
335	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1042	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1062641	2026-10-26 04:53:01+00	phone_server_anchor	500	f	\N	\N	\N	t	68	valid	f	\N	\N	\N	\N	\N	2026-10-26 04:53:02.729734+00
337	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1045	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1065664	2026-10-26 04:53:04+00	phone_server_anchor	500	f	\N	\N	\N	t	109	valid	f	\N	\N	\N	\N	\N	2026-10-26 04:53:06.918512+00
338	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1046	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1066673	2026-10-26 04:53:05+00	phone_server_anchor	500	f	\N	\N	\N	t	109	valid	f	\N	\N	\N	\N	\N	2026-10-26 04:53:06.918512+00
339	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1047	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1067680	2026-10-26 04:53:06+00	phone_server_anchor	500	f	\N	\N	\N	t	109	valid	f	\N	\N	\N	\N	\N	2026-10-26 04:53:06.918512+00
340	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1048	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1068687	2026-10-26 04:53:06+00	phone_server_anchor	500	f	\N	\N	\N	t	109	valid	f	\N	\N	\N	\N	\N	2026-10-26 04:53:09.089598+00
341	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1054	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1074733	2026-10-26 04:53:12+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	warming_up	f	\N	\N	\N	\N	\N	2026-10-26 04:53:15.225812+00
342	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1055	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1075740	2026-10-26 04:53:13+00	phone_server_anchor	500	f	\N	\N	\N	t	110	valid	f	\N	\N	\N	\N	\N	2026-10-26 04:53:15.225812+00
345	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1064	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1084809	2026-10-26 04:53:23+00	phone_server_anchor	500	f	\N	\N	\N	t	77	valid	f	\N	\N	\N	\N	\N	2026-10-26 04:53:25.57851+00
346	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1065	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1085817	2026-10-26 04:53:24+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:53:25.57851+00
347	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1066	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1086825	2026-10-26 04:53:25+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:53:27.848035+00
348	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1067	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1087832	2026-10-26 04:53:26+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	warming_up	f	\N	\N	\N	\N	\N	2026-10-26 04:53:27.848035+00
349	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1073	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1093879	2026-10-26 04:53:32+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	warming_up	f	\N	\N	\N	\N	\N	2026-10-26 04:53:33.968626+00
350	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1074	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1094886	2026-10-26 04:53:33+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	warming_up	f	\N	\N	\N	\N	\N	2026-10-26 04:53:36.104595+00
351	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1075	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1095894	2026-10-26 04:53:34+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	warming_up	f	\N	\N	\N	\N	\N	2026-10-26 04:53:36.104595+00
352	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1082	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1102947	2026-10-26 04:53:41+00	phone_server_anchor	500	f	\N	\N	\N	t	49	valid	f	\N	\N	\N	\N	\N	2026-10-26 04:53:42.191755+00
353	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1083	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1103954	2026-10-26 04:53:42+00	phone_server_anchor	500	f	\N	\N	\N	t	49	valid	f	\N	\N	\N	\N	\N	2026-10-26 04:53:44.32989+00
354	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1084	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1104963	2026-10-26 04:53:43+00	phone_server_anchor	500	f	\N	\N	\N	t	49	valid	f	\N	\N	\N	\N	\N	2026-10-26 04:53:44.32989+00
355	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1085	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1105970	2026-10-26 04:53:44+00	phone_server_anchor	500	f	\N	\N	\N	t	41	valid	f	\N	\N	\N	\N	\N	2026-10-26 04:53:46.477402+00
356	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1087	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1107986	2026-10-26 04:53:46+00	phone_server_anchor	500	f	\N	\N	\N	t	59	valid	f	\N	\N	\N	\N	\N	2026-10-26 04:53:48.608444+00
357	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1088	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1108992	2026-10-26 04:53:47+00	phone_server_anchor	500	f	\N	\N	\N	t	76	valid	f	\N	\N	\N	\N	\N	2026-10-26 04:53:48.608444+00
358	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1089	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1110001	2026-10-26 04:53:48+00	phone_server_anchor	500	f	\N	\N	\N	t	105	valid	f	\N	\N	\N	\N	\N	2026-10-26 04:53:50.73321+00
359	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1090	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1111009	2026-10-26 04:53:49+00	phone_server_anchor	500	f	\N	\N	\N	t	105	valid	f	\N	\N	\N	\N	\N	2026-10-26 04:53:50.73321+00
360	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1099	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1120076	2026-10-26 04:53:58+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:54:00.842784+00
361	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1100	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1121085	2026-10-26 04:53:59+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:54:00.842784+00
362	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1101	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1122092	2026-10-26 04:54:00+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:54:03.025533+00
363	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1102	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1123099	2026-10-26 04:54:00+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:54:03.025533+00
364	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1125	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1146276	2026-10-26 04:54:23+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:54:27.23788+00
365	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1126	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1147280	2026-10-26 04:54:25+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:54:27.23788+00
366	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1152	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1173579	2026-10-26 04:54:51+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:54:53.383905+00
367	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1153	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1174585	2026-10-26 04:54:52+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:54:55.513311+00
368	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1154	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1175593	2026-10-26 04:54:53+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:54:55.513311+00
369	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1165	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1186676	2026-10-26 04:55:05+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:55:07.625234+00
370	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1166	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1187683	2026-10-26 04:55:05+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:55:07.625234+00
371	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1175	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1196749	2026-10-26 04:55:14+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:55:17.793389+00
372	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1214	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1236041	2026-10-26 04:55:53+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:55:56.080687+00
373	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1215	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1237046	2026-10-26 04:55:55+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:55:56.080687+00
374	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1219	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1241076	2026-10-26 04:55:59+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:56:00.219171+00
378	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1231	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1253167	2026-10-26 04:56:11+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:56:12.660777+00
383	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1242	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1264250	2026-10-26 04:56:22+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:56:25.109371+00
384	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1243	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1265257	2026-10-26 04:56:23+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:56:25.109371+00
389	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1249	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1271303	2026-10-26 04:56:29+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:56:31.437327+00
390	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1250	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1272314	2026-10-26 04:56:30+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:56:31.437327+00
391	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1256	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1278360	2026-10-26 04:56:36+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:56:37.543245+00
397	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1273	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1295484	2026-10-26 04:56:53+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:56:56.150045+00
398	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1274	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1296494	2026-10-26 04:56:54+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:56:56.150045+00
399	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1280	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1302536	2026-10-26 04:57:00+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:57:02.242792+00
400	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1281	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1303543	2026-10-26 04:57:01+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:57:04.392318+00
401	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1282	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1304549	2026-10-26 04:57:02+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:57:04.392318+00
402	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1287	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1309587	2026-10-26 04:57:07+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:57:10.536493+00
403	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1288	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1310594	2026-10-26 04:57:08+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:57:10.536493+00
404	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1289	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1311603	2026-10-26 04:57:09+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:57:10.536493+00
405	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1300	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1322683	2026-10-26 04:57:20+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:57:22.746271+00
406	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1301	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1323691	2026-10-26 04:57:21+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:57:22.746271+00
411	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1312	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1334772	2026-10-26 04:57:32+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:57:35.230333+00
412	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1319	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1341825	2026-10-26 04:57:39+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:57:41.326311+00
417	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1330	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1352905	2026-10-26 04:57:50+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:57:53.87151+00
418	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1331	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1353912	2026-10-26 04:57:52+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:57:53.87151+00
419	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1332	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1354919	2026-10-26 04:57:53+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:57:53.87151+00
420	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1338	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1360965	2026-10-26 04:57:59+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:57:59.960596+00
431	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1380	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1403275	2026-10-26 04:58:40+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:58:43.00492+00
432	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1381	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1404283	2026-10-26 04:58:42+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:58:45.13547+00
433	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1382	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1405290	2026-10-26 04:58:43+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:58:45.13547+00
434	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1392	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1415365	2026-10-26 04:58:53+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:58:55.248487+00
435	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1393	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1416373	2026-10-26 04:58:54+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:58:57.371804+00
436	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1394	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1417379	2026-10-26 04:58:55+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:58:57.371804+00
437	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1401	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1424431	2026-10-26 04:59:02+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:59:03.468735+00
440	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1404	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1427454	2026-10-26 04:59:05+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:59:07.689843+00
442	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1416	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1439546	2026-10-26 04:59:17+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:59:20.951507+00
443	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1417	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1440552	2026-10-26 04:59:18+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:59:20.951507+00
375	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1220	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1242083	2026-10-26 04:56:00+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:56:02.350934+00
376	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1221	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1243091	2026-10-26 04:56:01+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:56:02.350934+00
377	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1222	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1244098	2026-10-26 04:56:02+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:56:04.548632+00
379	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1232	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1254174	2026-10-26 04:56:12+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:56:14.79902+00
380	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1233	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1255182	2026-10-26 04:56:13+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:56:14.79902+00
381	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1234	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1256189	2026-10-26 04:56:14+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:56:16.927046+00
382	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1241	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1263243	2026-10-26 04:56:21+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:56:23.025775+00
385	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1244	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1266265	2026-10-26 04:56:24+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:56:27.204886+00
386	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1246	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1268281	2026-10-26 04:56:26+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:56:27.204886+00
387	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1247	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1269288	2026-10-26 04:56:27+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:56:29.292449+00
388	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1248	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1270296	2026-10-26 04:56:28+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:56:29.292449+00
392	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1257	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1279367	2026-10-26 04:56:37+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:56:39.65435+00
393	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1258	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1280374	2026-10-26 04:56:38+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:56:39.65435+00
394	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1259	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1281383	2026-10-26 04:56:39+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:56:41.903728+00
395	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1271	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1293469	2026-10-26 04:56:51+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:56:54.054017+00
396	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1272	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1294477	2026-10-26 04:56:52+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:56:54.054017+00
407	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1302	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1324698	2026-10-26 04:57:22+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:57:24.840856+00
408	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1309	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1331751	2026-10-26 04:57:29+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:57:30.942498+00
409	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1310	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1332758	2026-10-26 04:57:30+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:57:33.088129+00
410	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1311	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1333765	2026-10-26 04:57:31+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:57:33.088129+00
413	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1320	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1342832	2026-10-26 04:57:40+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:57:43.489315+00
414	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1321	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1343839	2026-10-26 04:57:42+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:57:43.489315+00
415	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1322	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1344847	2026-10-26 04:57:42+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:57:45.62852+00
416	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1329	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1351897	2026-10-26 04:57:49+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:57:51.740842+00
421	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1339	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1361972	2026-10-26 04:58:00+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:58:02.06266+00
422	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1340	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1362980	2026-10-26 04:58:01+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:58:02.06266+00
423	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1341	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1363987	2026-10-26 04:58:01+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:58:04.184715+00
424	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1357	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1380106	2026-10-26 04:58:18+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:58:20.358841+00
425	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1358	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1381114	2026-10-26 04:58:19+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:58:20.358841+00
426	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1359	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1382119	2026-10-26 04:58:20+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:58:22.519464+00
427	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1360	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1383126	2026-10-26 04:58:21+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:58:22.519464+00
428	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1370	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1393200	2026-10-26 04:58:31+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:58:32.628221+00
429	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1371	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1394207	2026-10-26 04:58:32+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:58:34.893285+00
430	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1372	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1395216	2026-10-26 04:58:32+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:58:34.893285+00
438	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1402	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1425438	2026-10-26 04:59:03+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:59:05.584526+00
439	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1403	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1426446	2026-10-26 04:59:04+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:59:05.584526+00
441	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1415	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1438538	2026-10-26 04:59:16+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:59:17.767972+00
444	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1434	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1457737	2026-10-26 04:59:35+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:59:39.066462+00
445	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1435	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1458745	2026-10-26 04:59:36+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:59:39.066462+00
446	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1436	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1459753	2026-10-26 04:59:37+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:59:41.129809+00
447	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1439	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1462775	2026-10-26 04:59:40+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:59:45.694829+00
448	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1440	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1463782	2026-10-26 04:59:41+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:59:45.694829+00
449	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1441	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1464791	2026-10-26 04:59:42+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:59:47.74885+00
450	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1442	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1465798	2026-10-26 04:59:43+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:59:47.74885+00
451	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1449	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1472849	2026-10-26 04:59:50+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:59:51.827362+00
452	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1450	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1473857	2026-10-26 04:59:51+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:59:53.9909+00
453	904229f7-6dee-5ce6-85cb-51227471b2f4	unknown	1451	30f11f19-c0bf-4c64-a167-6a0ec697e18b	1474865	2026-10-26 04:59:52+00	phone_server_anchor	500	f	\N	\N	\N	f	\N	no_contact	f	\N	\N	\N	\N	\N	2026-10-26 04:59:53.9909+00
\.


--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: catch_me
--

COPY public.users (id, username, password_hash, display_name, points_balance, lifetime_xp, location_sharing, created_at) FROM stdin;
8c52d6e8-0d44-52d4-91d0-e05fefbb572e	toma	pbkdf2_sha256$260000$j5N+5H67uMiNyTMJIZ9Izg==$DIrF7PzrFoOAJT8R3Fi4NAAmbZoI2bEaupilrlr7Xys=	Toma	100	100	t	2026-10-24 19:46:56.185741+00
9a032bc0-bbdf-5167-af46-0e0882a7db09	miya	pbkdf2_sha256$260000$RwrlwsDQQXi+8FB0Jfi5rA==$kOdhoHtakNdd59WbOGHufo+aXzv+JO2ynpmdgh9FZOQ=	Miya	50	100	t	2026-10-24 19:46:56.185741+00
\.


--
-- Name: point_transactions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: catch_me
--

SELECT pg_catalog.setval('public.point_transactions_id_seq', 3, true);


--
-- Name: telemetry_records_id_seq; Type: SEQUENCE SET; Schema: public; Owner: catch_me
--

SELECT pg_catalog.setval('public.telemetry_records_id_seq', 453, true);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: catch_me
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: app_state app_state_pkey; Type: CONSTRAINT; Schema: public; Owner: catch_me
--

ALTER TABLE ONLY public.app_state
    ADD CONSTRAINT app_state_pkey PRIMARY KEY (key);


--
-- Name: devices devices_firmware_alias_key; Type: CONSTRAINT; Schema: public; Owner: catch_me
--

ALTER TABLE ONLY public.devices
    ADD CONSTRAINT devices_firmware_alias_key UNIQUE (firmware_alias);


--
-- Name: devices devices_pkey; Type: CONSTRAINT; Schema: public; Owner: catch_me
--

ALTER TABLE ONLY public.devices
    ADD CONSTRAINT devices_pkey PRIMARY KEY (id);


--
-- Name: login_sessions login_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: catch_me
--

ALTER TABLE ONLY public.login_sessions
    ADD CONSTRAINT login_sessions_pkey PRIMARY KEY (id);


--
-- Name: login_sessions login_sessions_token_hash_key; Type: CONSTRAINT; Schema: public; Owner: catch_me
--

ALTER TABLE ONLY public.login_sessions
    ADD CONSTRAINT login_sessions_token_hash_key UNIQUE (token_hash);


--
-- Name: owned_rewards owned_rewards_pkey; Type: CONSTRAINT; Schema: public; Owner: catch_me
--

ALTER TABLE ONLY public.owned_rewards
    ADD CONSTRAINT owned_rewards_pkey PRIMARY KEY (user_id, reward_id);


--
-- Name: pairings pairings_pkey; Type: CONSTRAINT; Schema: public; Owner: catch_me
--

ALTER TABLE ONLY public.pairings
    ADD CONSTRAINT pairings_pkey PRIMARY KEY (id);


--
-- Name: point_transactions point_transactions_pkey; Type: CONSTRAINT; Schema: public; Owner: catch_me
--

ALTER TABLE ONLY public.point_transactions
    ADD CONSTRAINT point_transactions_pkey PRIMARY KEY (id);


--
-- Name: quest_awards quest_awards_pkey; Type: CONSTRAINT; Schema: public; Owner: catch_me
--

ALTER TABLE ONLY public.quest_awards
    ADD CONSTRAINT quest_awards_pkey PRIMARY KEY (id);


--
-- Name: quest_sessions quest_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: catch_me
--

ALTER TABLE ONLY public.quest_sessions
    ADD CONSTRAINT quest_sessions_pkey PRIMARY KEY (id);


--
-- Name: rewards rewards_pkey; Type: CONSTRAINT; Schema: public; Owner: catch_me
--

ALTER TABLE ONLY public.rewards
    ADD CONSTRAINT rewards_pkey PRIMARY KEY (id);


--
-- Name: session_participants session_participants_pkey; Type: CONSTRAINT; Schema: public; Owner: catch_me
--

ALTER TABLE ONLY public.session_participants
    ADD CONSTRAINT session_participants_pkey PRIMARY KEY (session_id, user_id);


--
-- Name: telemetry_records telemetry_records_pkey; Type: CONSTRAINT; Schema: public; Owner: catch_me
--

ALTER TABLE ONLY public.telemetry_records
    ADD CONSTRAINT telemetry_records_pkey PRIMARY KEY (id);


--
-- Name: quest_awards uq_award_once; Type: CONSTRAINT; Schema: public; Owner: catch_me
--

ALTER TABLE ONLY public.quest_awards
    ADD CONSTRAINT uq_award_once UNIQUE (session_id, user_id);


--
-- Name: pairings uq_pairings_user_a; Type: CONSTRAINT; Schema: public; Owner: catch_me
--

ALTER TABLE ONLY public.pairings
    ADD CONSTRAINT uq_pairings_user_a UNIQUE (user_a_id);


--
-- Name: pairings uq_pairings_user_b; Type: CONSTRAINT; Schema: public; Owner: catch_me
--

ALTER TABLE ONLY public.pairings
    ADD CONSTRAINT uq_pairings_user_b UNIQUE (user_b_id);


--
-- Name: point_transactions uq_purchase_idempotency; Type: CONSTRAINT; Schema: public; Owner: catch_me
--

ALTER TABLE ONLY public.point_transactions
    ADD CONSTRAINT uq_purchase_idempotency UNIQUE (user_id, idempotency_key);


--
-- Name: telemetry_records uq_telemetry_identity; Type: CONSTRAINT; Schema: public; Owner: catch_me
--

ALTER TABLE ONLY public.telemetry_records
    ADD CONSTRAINT uq_telemetry_identity UNIQUE (device_id, boot_id, sequence);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: catch_me
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: users users_username_key; Type: CONSTRAINT; Schema: public; Owner: catch_me
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_username_key UNIQUE (username);


--
-- Name: ix_devices_owner_user_id; Type: INDEX; Schema: public; Owner: catch_me
--

CREATE INDEX ix_devices_owner_user_id ON public.devices USING btree (owner_user_id);


--
-- Name: ix_login_sessions_user_id; Type: INDEX; Schema: public; Owner: catch_me
--

CREATE INDEX ix_login_sessions_user_id ON public.login_sessions USING btree (user_id);


--
-- Name: ix_point_transactions_user_id; Type: INDEX; Schema: public; Owner: catch_me
--

CREATE INDEX ix_point_transactions_user_id ON public.point_transactions USING btree (user_id);


--
-- Name: ix_telemetry_session; Type: INDEX; Schema: public; Owner: catch_me
--

CREATE INDEX ix_telemetry_session ON public.telemetry_records USING btree (session_id, device_id, captured_at);


--
-- Name: devices devices_owner_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: catch_me
--

ALTER TABLE ONLY public.devices
    ADD CONSTRAINT devices_owner_user_id_fkey FOREIGN KEY (owner_user_id) REFERENCES public.users(id);


--
-- Name: login_sessions login_sessions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: catch_me
--

ALTER TABLE ONLY public.login_sessions
    ADD CONSTRAINT login_sessions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: owned_rewards owned_rewards_reward_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: catch_me
--

ALTER TABLE ONLY public.owned_rewards
    ADD CONSTRAINT owned_rewards_reward_id_fkey FOREIGN KEY (reward_id) REFERENCES public.rewards(id);


--
-- Name: owned_rewards owned_rewards_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: catch_me
--

ALTER TABLE ONLY public.owned_rewards
    ADD CONSTRAINT owned_rewards_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: pairings pairings_user_a_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: catch_me
--

ALTER TABLE ONLY public.pairings
    ADD CONSTRAINT pairings_user_a_id_fkey FOREIGN KEY (user_a_id) REFERENCES public.users(id);


--
-- Name: pairings pairings_user_b_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: catch_me
--

ALTER TABLE ONLY public.pairings
    ADD CONSTRAINT pairings_user_b_id_fkey FOREIGN KEY (user_b_id) REFERENCES public.users(id);


--
-- Name: point_transactions point_transactions_reward_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: catch_me
--

ALTER TABLE ONLY public.point_transactions
    ADD CONSTRAINT point_transactions_reward_id_fkey FOREIGN KEY (reward_id) REFERENCES public.rewards(id);


--
-- Name: point_transactions point_transactions_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: catch_me
--

ALTER TABLE ONLY public.point_transactions
    ADD CONSTRAINT point_transactions_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.quest_sessions(id);


--
-- Name: point_transactions point_transactions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: catch_me
--

ALTER TABLE ONLY public.point_transactions
    ADD CONSTRAINT point_transactions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: quest_awards quest_awards_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: catch_me
--

ALTER TABLE ONLY public.quest_awards
    ADD CONSTRAINT quest_awards_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.quest_sessions(id);


--
-- Name: quest_awards quest_awards_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: catch_me
--

ALTER TABLE ONLY public.quest_awards
    ADD CONSTRAINT quest_awards_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: quest_sessions quest_sessions_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: catch_me
--

ALTER TABLE ONLY public.quest_sessions
    ADD CONSTRAINT quest_sessions_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: session_participants session_participants_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: catch_me
--

ALTER TABLE ONLY public.session_participants
    ADD CONSTRAINT session_participants_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.quest_sessions(id);


--
-- Name: session_participants session_participants_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: catch_me
--

ALTER TABLE ONLY public.session_participants
    ADD CONSTRAINT session_participants_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: telemetry_records telemetry_records_device_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: catch_me
--

ALTER TABLE ONLY public.telemetry_records
    ADD CONSTRAINT telemetry_records_device_id_fkey FOREIGN KEY (device_id) REFERENCES public.devices(id);


--
-- Name: telemetry_records telemetry_records_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: catch_me
--

ALTER TABLE ONLY public.telemetry_records
    ADD CONSTRAINT telemetry_records_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.quest_sessions(id);


--
-- PostgreSQL database dump complete
--

\unrestrict hVFeGv6Xd5VxlC9cRAhjtoFzdTZpukhs7uPytZPQkILH7pdStuVkKtF60IcXZcb


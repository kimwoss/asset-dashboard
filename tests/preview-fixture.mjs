// Synthetic values only. This module is never included in the production build.
export function fixture() {
  const now = new Date(), iso = now.toISOString(), day = new Date(+now + 9*3600e3).toISOString().slice(0,10);
  const stock = (owner, account, group, name, ticker, value, div) => ({ owner, account, group, name, ticker, currency:"KRW", qty:1000, price:value/1000, value_krw:value, div_krw:div, div_net_krw:div*.846, tax_rate:.154, div_months:Array(12).fill(div/12), div_kinds:Array(12).fill("est") });
  const holdings=[
    stock("우현","일반계좌","유동성","TIGER 미국S&P500","KRX:360750",320000000,4800000),
    stock("규리","일반계좌","유동성","TIGER 미국배당다우존스","KRX:458730",180000000,6500000),
    stock("우현","연금저축","연금성","KODEX 미국나스닥100","KRX:379810",140000000,1400000),
    stock("규리","IRP","연금성","RISE 200","KRX:148020",60000000,1800000)
  ];
  const financial={year:2026,fx:1370,holdings,quotes_asof:iso};
  const fire={target_basic:2200000000,target_rich:2800000000,target_year:2028,target_month:4,monthly_expense:5500000,current_age:40,retire_age:42,age_self:"우현",age_spouse:"규리",age_gap:8,real_return:4,life_expectancy:100};
  const assets=[{name:"부동산 A",owner:"우현",category:"부동산",value_krw:1150000000},{name:"부동산 B",owner:"규리",category:"부동산",value_krw:850000000},{name:"우현 금융",owner:"우현",category:"주식",value_krw:460000000},{name:"규리 금융",owner:"규리",category:"주식",value_krw:240000000},{name:"거주 보증금",owner:"공동",category:"전세보증금",value_krw:200000000},{name:"생활 예비비",owner:"공동",category:"현금",value_krw:50000000}];
  const liabilities=[{name:"주택 담보",owner:"공동",kind:"담보",target:"부동산 A",amount_krw:1000000000}];
  const months=["2026-07","2026-08","2026-09","2026-10"];
  const spending={year:2026,months,closed:3,total:[4200000,4600000,4400000,3100000],categories:[{name:"생활",values:[1600000,1500000,1600000,1200000]},{name:"여행",values:[1200000,1700000,1300000,800000]},{name:"외식",values:[800000,800000,900000,600000]},{name:"기타",values:[600000,600000,600000,500000]}]};
  const officetel={cap_man:90000,area_min:13,criteria:"샘플 조건 · 환산전세 9억 이하",summary:{ok:3,listed:3,total:3,buildings:3,min_conv:72000},deals:{},items:[
    {name:"브라이튼 여의도",region:"서울 영등포구",type:"59A",area:17.8,rooms:"방 2 · 욕실 1",deposit:30000,monthly:180,converted:75000,ok:true,listed:true,floor:"중층",facing:"남향",asof:day,link:"https://land.naver.com/",stars:"★★"},
    {name:"힐스테이트 여의도",region:"서울 영등포구",type:"49B",area:15.2,rooms:"방 1 · 욕실 1",deposit:50000,monthly:100,converted:75000,ok:true,listed:true,floor:"고층",facing:"동향",asof:day,link:"https://land.naver.com/",stars:"★★"},
    {name:"여의도 더원",region:"서울 영등포구",type:"49A",area:14.9,rooms:"방 1 · 욕실 1",deposit:40000,monthly:128,converted:72000,ok:true,listed:true,floor:"고층",facing:"남서향",asof:day,link:"https://land.naver.com/",stars:"★"}
  ]};
  const checkpoint={generated_at:iso,date_label:"디자인 검증용 샘플",weather:"서울 18° · 맑음",greeting:"오늘의 변화를 차분히 살펴보세요.",summary:"모든 숫자와 매물 조건은 화면 확인을 위한 가상 데이터입니다.",us:[{name:"S&P 500",price:6000,unit:"pt",change_pct:.42},{name:"나스닥",price:20000,unit:"pt",change_pct:.63}],kr:[{name:"TIGER 미국S&P500",price:32000,change_pct:.35}],fx:[{name:"USD/KRW",rate:1370,change_pct:-.12}],news:[{title:"샘플 뉴스 · 출처와 발표 시각을 함께 확인하세요",source:"미리보기",link:"https://www.wealthfront.com/"}],fear_greed:{score:55,label:"중립"}};
  const city=(name,avg)=>({name,avg_monthly:avg,annual_budget:avg*12,fire_target:avg*400,categories:[avg*.4,avg*.35,avg*.25]});
  const cities={seoul:city("서울, 한국",5500000),cities:[city("포르투, 포르투갈",3800000),city("후쿠오카, 일본",4200000)],categories:[{name:"주거"},{name:"생활"},{name:"여행"}]};
  const simulation={retire_age:42,summary:{retire_asset:2200000000,real_net_end:500000000},series:Array.from({length:20},(_,i)=>({age:40+i,year:2026+i,phase:i===0?"현재":i<2?"준비":"은퇴",net:1850000000+i*30000000,real_net:1850000000+i*10000000,invest:100000000,spend:66000000,medical:3000000,pension:0,retire_income:0,saving:24000000}))};
  const review={years:[2026],byYear:{"2026":{best:[{label:"여행",text:"함께 걷는 다음 여정"}],months:[]}}};
  const snap={updated_at:iso,fx_usdkrw:1370,assets,liabilities,gross_krw:2950000000,debt_krw:1000000000,net_krw:1950000000,total_krw:1950000000,financial,fire,spending,officetel,checkpoint,cities,simulation,review,prev_day:{net_krw:1943000000,key:day},prev_month:{net_krw:1900000000,key:"2026-09"},prev_year:{net_krw:1700000000,key:"2025"}};
  const keys=["financial","news","checkpoint","spending","fire","simulation","liabilities","officetel","cities"];
  const live={updated_iso:iso,updated_at:iso,financial,fire,spending,officetel,checkpoint,cities,simulation,review,liabilities,news:checkpoint.news,us:checkpoint.us,kr:checkpoint.kr,fx:checkpoint.fx,_fetched:Object.fromEntries(keys.map(k=>[k,iso])),_status:Object.fromEntries(keys.map(k=>[k,{state:"ok"}]))};
  const history="date,name,value\n2025-12-31,total,1700000000\n2026-07-31,total,1800000000\n2026-08-31,total,1840000000\n2026-09-30,total,1900000000\n";
  return {snap,live,history};
}

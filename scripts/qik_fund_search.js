(function () {
  let _filter = null;
  const btn_tgl = ".box-fundsearch .btn-toggle";
  const $keyword = $(`${btn_tgl} [name='check_01']`);
  const $assets = $(`${btn_tgl} [name='check_02']`);
  const $region = $(`${btn_tgl} [name='check_03']`);
  const $frequency = $(`${btn_tgl} [name='check_04']`);
  const $nisa_label = $(".information");
  const $nisag = $("#check_01-01");
  const $nisat = $("#check_01-02");

  let freeword = "";
  let select_companies = {securities: [], banks: []};
  let fav_list = [];
  
  const writeRecentlyViewCompany = () => {
    const domain = config.recently.cookie.domain;
    const path = config.recently.cookie.path;
    const maxage = config.recently.cookie.maxage
    const secure = config.recently.cookie.secure;
    const params = `domain=${domain}; path=${path}; max-age=${maxage}; ${secure}`;
    document.cookie = `${config.recently.cookie.name.securities}=${select_companies.securities.slice(-5).join(",")}; ${params}`;
    document.cookie = `${config.recently.cookie.name.banks}=${select_companies.banks.slice(-5).join(",")}; ${params}`;
  }
  
  const readRecentlyViewCompany = () => {
    let result = {securities: [], banks: []};
    const cookies = document.cookie;
    const array = cookies.split("; ");
    array.forEach(v => {
      const content = v.split('=');
      if (content.length > 1) {
        if (content[0] == config.recently.cookie.name.securities) {
          result.securities = content[1] ? content[1].split(",") : [];
        }
        else if (content[0] == config.recently.cookie.name.banks) {
          result.banks = content[1] ? content[1].split(",") : [];
        }
      }
    });
    return (result);
  }
  
  const ajaxError = () => {
    $(".box-notice.error").show();
  }
  
  const dispLoading = () => {
    if($("#loading").length == 0){
      $("body").append("<div id='loading'><img src='../common/images/ico_movie_loading_01.svg' alt='loading'></div>");
    }
  }
  
  const removeLoading = () => {
    $("#loading").remove();
  }
  
  const sendLog = (genre, cond) => {
    let params = `?genre=${genre}&condition=${cond}`;
    $.ajax({
      type: "GET",
      url: `${config.log.url}${params}`
    });
  }
  
  const initTab = (p) => {
    let tab = p.get("tab");
    if (tab != "1" && tab != "2") {
      tab = "1";
    }
    $(`input#tab_02-0${tab}`).prop("checked", true);
    $(".tbl-fundsearch")
      .removeClass("basic-information")
      .removeClass("return")
      .addClass($(`input#tab_02-0${tab}`).attr("data-tab-switch"));
  }
  
  const initSort = (p) => {
    let sort = p.get("sort") || "1";
    let sort_type = "";
    switch (sort.replace(/\-/g, "")) {
      case "1": sort_type = "name"; break;
      case "2": sort_type = "nav"; break;
      case "3": sort_type = "chgv"; break;
      case "4": sort_type = "chgr"; break;
      case "5": sort_type = "tav"; break;
      case "6": sort_type = "rtnd"; break;
      case "7": sort_type = "rtn1m"; break;
      case "8": sort_type = "rtn3m"; break;
      case "9": sort_type = "rtn6m"; break;
      case "10": sort_type = "rtn1y"; break;
      case "11": sort_type = "rtn3y"; break;
      case "12": sort_type = "rtn5y"; break;
      case "13": sort_type = "rtnall"; break;
    }
    if (sort_type) {
      let dir = /^-.*$/g.test(sort) ? "down" : "up"
      $(`.sort-switch[data-sort="${sort_type}"]`).addClass(dir);
    }
  }
  
  const initFreeword = (p, data) => {
    let $freeword = $("#qik_freeword");
    let text = p.get("text");
    if (text) {
      $freeword.val(text.trim());
    }
    else {
      let category = p.get("category");
      if (data.status == 0 && data.hitcount > 0) {
        if (data.data[category]) {
          $freeword.val(data.data[category].CategoryName);
        }
      }
    }
    freeword = $freeword.val();
  };
  
  const initCheckbox = (p) => {
    for (const [key, value] of p.entries()) {
      if (key == "company") {
        let has_securities = false;
        let has_banks = false;
        for (let code of value ? value.split(",") : []) {
          let $checkbox = $(`.box-fundsearch .sales [type='checkbox'][value=${code}]`);
          $checkbox.prop("checked", true);
          let type = $checkbox.attr("name");
          if (has_securities == false) {
            has_securities = type == "securities";
          }
          if (has_banks == false) {
            has_banks = type == "banks" || type == "insurance" || type == "shortTerm";
          }
        }
        if (has_securities == true) {
          $(".btn-select[data-modal='securities']").addClass("is-selected");
        }
        if (has_banks == true) {
          $(".btn-select[data-modal='banksetc']").addClass("is-selected");
        }
      }
      else {
        let name =
          key == "keyword" ? "check_01" :
          key == "asset" ? "check_02":
          key == "region" ? "check_03":
          key == "frequency" ? "check_04":
          "";
        if (name) {
          for (let val of value.split(",")) {
            if (val) {
              const $chkbox = $(`${btn_tgl} [name=${name}][value=${val}]`);
              $chkbox.prop("checked", true);
              $target_block = $chkbox.closest(".blk-conditions");
              if (!$target_block.hasClass("has_checked")) {
                $target_block.addClass("has_checked");
              }
              
              // よく選択される条件ボタンの選択
              $often_btn = $(`.btn-often-selected[data-id="${$chkbox.attr('id')}"]`);
              if ($often_btn.length > 0 &&
                  $often_btn.parent().css("display") != "none") {
                $often_btn.addClass("is-selected");
                $target_block.addClass("is-open");
              }
            }
          }
        }
      }
    }
    
    $nisa_label.removeClass("has_nisa-label");
    if ($nisag.prop("checked") == true || $nisat.prop("checked") == true) {
      $nisa_label.addClass("has_nisa-label");
    }
  } 
  
  const getCompanyInfo = () => {
    return ($.ajax({
      type: "GET",
      url: "../cgi/wrap/qjsonp.aspx?F=ctl/fund_company",
      dataType : "jsonp",
      timeout: 10000,
      cache: false
    }));
  }
  
  const getProductClassInfo = () => {
    return ($.ajax({
      type: "GET",
      url: "../cgi/wrap/qjsonp.aspx?F=ctl/fund_prod_class",
      dataType : "jsonp",
      timeout: 10000,
      cache: false
    }));
  }
  
  const getOftenSelectedInfo = () => {
    return ($.ajax({
      type: "GET",
      url: "../cgi/wrap/qjsonp.aspx?F=ctl/fund_often_selected",
      dataType : "jsonp",
      timeout: 10000,
      cache: false
    }));
  }
  
  const scrollSearchResult = () => {
    var h = $("#site-header").outerHeight();
    var target = $("#searchResult");
    if ($("body").hasClass("nav-opened")) $("body").removeClass("nav-opened");
    if (target.length) {
      $("html,body").animate({
        scrollTop: target.offset().top - h
      }, 1000);
    }
  }
  
  let _companyData = [];
  let _fundData = [];
  const getFundInfo = (f, c, j, cl) => {
    const getJson = (f, c) => {
      const changeSpecialCharacter = (str) => {
        var enc_str = encodeURI(str);
        enc_str = enc_str.replace(/%C2%A5/gi, "%5C");
        enc_str = enc_str.replace(/%5C/gi, "%EF%BF%A5");
        str = decodeURI(enc_str);
        let result = str
          .replace(/\(/g, '（')
          .replace(/\)/g, '）')
          .replace(/\-/g, '－')
          .replace(/\+/g, '＋')
          .replace(/\*/g, '＊')
          .replace(/\'/g, '’')
          .replace(/\!/g, '！')
          .replace(/\"/g, '”')
          .replace(/\&/g, '＆')
          .replace(/\|/g, '｜')
          .replace(/\</g, '＜')
          .replace(/\>/g, '＞')
          .replace(/\\/g, '￥')
          .replace(/\`/g, '‘')
          .replace(/\#/g, '＃')
          .replace(/\?/g, '？')
          .replace(/\@/g, '＠')
          .replace(/:/g, '：')
          .replace(/\xAE/g, '（R）'); // ®(登録商標)
        return (result);
      }
      
      return ($.ajax({
        type: "GET",
        url: "../cgi/wrap/qjsonp.aspx?F=ctl/fund_search",
        dataType : "jsonp",
        data: {"KEY1": changeSpecialCharacter(f), "KEY2": changeSpecialCharacter(c)},
        timeout: 10000,
        cache: false
      }));
    }
    
    dispLoading();
    let _cl = cl;
    return $.when(getJson(f, c).done((r, s, x) => {
      _fundData = [];
      if (r.section1.status == 0) {
        if (r.section1.data) {
          if (_companyData.length == 0 && _cl) {
            _companyData = _cl.data;
          }
          _fundData = r.section1.data;
        }
        undateFundCount(null);
        createTable();
        $(".box-fundsearch, .box-accordion-fundsearch, .box-control, .blk-quick").show();
        if (j) {
          let p = new URLSearchParams(location.search);
          if (p.size > 1) {
            let jump = false;
            for (const [key, value] of p.entries()) {
              jump = key == "text" ||
                    key == "category" ||
                    key == "keyword" ||
                    key == "asset" ||
                    key == "region" ||
                    key == "frequency" ||
                    key == "company";
              if (jump) {
                break;
              } 
            }
            if (jump) {
              $("a.btn-search-confirm").click();
            }
          }
        }
      }
      else {
        ajaxError();
      }
    }).fail((x, s, e) => {
      ajaxError();
    }).always((r, s, e) => {
      removeLoading();
    }));
  }
  
  const updateUrl = () => {
    let keywords = [];
    let assets = [];
    let regions = [];
    let frequencies = [];
    let companies = [];
    
    const text = $("#qik_freeword").val();
    
    $(`[type='checkbox']:checked`).each((idx, elm) => {
      let name = $(elm).attr("name");
      switch (name) {
        case "check_01":
          keywords.push($(elm).val());
          break;
          
        case "check_02":
          assets.push($(elm).val());
          break;
          
        case "check_03":
          regions.push($(elm).val());
          break;
          
        case "check_04":
          frequencies.push($(elm).val());
          break;
          
        case "securities":
        case "banks":
        case "insurance":
        case "shortTerm":
          companies.push($(elm).val());
          break;
      }
    });
    
    const tab = $("input#tab_02-01").prop("checked") == true ? "1" :
                $("input#tab_02-02").prop("checked") == true ? "2" : "1";
    
    const sort = $('.sort-switch[data-sort="name"]').hasClass("up") ? "1" :
                $('.sort-switch[data-sort="name"]').hasClass("down") ? "-1" :
                $('.sort-switch[data-sort="nav"]').hasClass("up") ? "2" :
                $('.sort-switch[data-sort="nav"]').hasClass("down") ? "-2" :
                $('.sort-switch[data-sort="chgv"]').hasClass("up") ? "3" :
                $('.sort-switch[data-sort="chgv"]').hasClass("down") ? "-3" :
                $('.sort-switch[data-sort="chgr"]').hasClass("up") ? "4" :
                $('.sort-switch[data-sort="chgr"]').hasClass("down") ? "-4" :
                $('.sort-switch[data-sort="tav"]').hasClass("up") ? "5" :
                $('.sort-switch[data-sort="tav"]').hasClass("down") ? "-5" :
                $('.sort-switch[data-sort="rtnd"]').hasClass("up") ? "6" :
                $('.sort-switch[data-sort="rtnd"]').hasClass("down") ? "-6" :
                $('.sort-switch[data-sort="rtn1m"]').hasClass("up") ? "7" :
                $('.sort-switch[data-sort="rtn1m"]').hasClass("down") ? "-7" :
                $('.sort-switch[data-sort="rtn3m"]').hasClass("up") ? "8" :
                $('.sort-switch[data-sort="rtn3m"]').hasClass("down") ? "-8" :
                $('.sort-switch[data-sort="rtn6m"]').hasClass("up") ? "9" :
                $('.sort-switch[data-sort="rtn6m"]').hasClass("down") ? "-9" :
                $('.sort-switch[data-sort="rtn1y"]').hasClass("up") ? "10" :
                $('.sort-switch[data-sort="rtn1y"]').hasClass("down") ? "-10" :
                $('.sort-switch[data-sort="rtn3y"]').hasClass("up") ? "11" :
                $('.sort-switch[data-sort="rtn3y"]').hasClass("down") ? "-11" :
                $('.sort-switch[data-sort="rtn5y"]').hasClass("up") ? "12" :
                $('.sort-switch[data-sort="rtn5y"]').hasClass("down") ? "-12" :
                $('.sort-switch[data-sort="rtnall"]').hasClass("up") ? "13" :
                $('.sort-switch[data-sort="rtnall"]').hasClass("down") ? "-13" : "1";
                
    let p = new URLSearchParams();
    if (text) {
      p.set("text", text);
    }
    if (keywords.length > 0) {
      p.set("keyword", keywords.join(","));
    }
    if (assets.length > 0) {
      p.set("asset", assets.join(","));
    }
    if (regions.length > 0) {
      p.set("region", regions.join(","));
    }
    if (frequencies.length > 0) {
      p.set("frequency", frequencies.join(","));
    }
    if (companies.length > 0) {
      p.set("company", companies.join(","));
    }
    p.set("tab", tab);
    p.set("sort", sort);
    let idx = location.href.indexOf("?");
    let delim = p.size > 0 ? "&" : "";
    let url = `${location.href.slice(0, idx)}?F=fund_search${delim}${p.toString()}`;
    history.pushState(null, null, url);
  }
  
  let _allSecurities = null;
  const mergeCompanyCode4ETF = () => {
    if (_allSecurities == null) {
      let allSecurities = [];
      if (_companyData) {
        for (let i = 0; i < _companyData.length; i++) {
          if (_companyData[i].CompanyType == "1") {
            allSecurities.push(_companyData[i].CompanyCode);
          }
        }
      }
      _allSecurities = allSecurities;
    }
    
    let p = new URLSearchParams(location.search);
    let codes = (p.get("company") ? p.get("company").split(",") : []).filter(code => {
      let cd = _companyData.filter(cc => {
        return (cc.CompanyCode == code);
      });
      return (cd && cd.length == 1 && cd[0].CompanyType == "1");
    });
    
    let data = _fundData.map(d => ({...d}));
    
    let hasPayPaySec = codes.indexOf("12960") >= 0;         // PayPay証券
    
    let noETFSecArray = [
      "12921",  // LINE証券
      "573",    // ゴールドマン・サックス証券
      "11638",  // ナティクシス日本証券
      "987",    // JPモルガン証券
      "11717",  // ジェフリーズ証券東京支店
      "721",    // UBS証券
      "902",    // ソシエテ・ジェネラル証券
      "571",    // シティグループ証券
      "12410",  // バークレイズ証券
      "618",    // BNPパリバ証券
      "12479",  // エービーエヌ・アムロ・クリアリング証券
      "550",    // BofA証券
      "575"     // モルガン・スタンレーMUFG証券
    ];
    let noETFSec = 0;
    noETFSecArray.forEach(c => {
      if (codes.indexOf(c) >= 0) {
        noETFSec++;
      }
    });
    
    const normalMerge = () => {
      data.forEach(e => {
        if (e.CNDKeyword.indexOf('3') >= 0) {
          e.CNDCompany = Array.from(new Set([...e.CNDCompany, ..._allSecurities]));
          e.CompanyCode = e.CNDCompany.join(" ");
        }
      });
    }
    const merge4PayPaySec = () => {
      data.forEach(e => {
        if (e.CNDKeyword.indexOf('3') >= 0 &&
            (e.NAMCode == "141321" ||
             e.NAMCode == "141571" ||
             e.NAMCode == "141357" ||
             e.NAMCode == "141570")) {
          e.CNDCompany = Array.from(new Set([...e.CNDCompany, ["12960"]]));
          e.CompanyCode = e.CNDCompany.join(" ");
        }
      });
    }
    const deleteSecFromETF = () => {
      data.forEach(e => {
        if (e.CNDKeyword.indexOf('3') >= 0) {
          e.CNDCompany = e.CNDCompany.filter(e => {
            return (noETFSecArray.indexOf(e) < 0);
          });
          e.CompanyCode = e.CNDCompany.join(" ");
        }
      });
    }
    if (codes.length == 1) {
      // PayPay証券のみ選択
      if (hasPayPaySec) {
        merge4PayPaySec();
      }
      // ETF非表示対象証券会社のみ選択
      else if (noETFSec > 0) {
        deleteSecFromETF();
      }
      // 上記以外
      else {
        normalMerge();
      }
    }
    else if (codes.length >= 2) {
      // PayPay証券とETF非表示対象証券を選択
      if (hasPayPaySec && noETFSec > 0 && codes.length == noETFSec + 1) {
        deleteSecFromETF();
        merge4PayPaySec();
      }
      // ETF非表示対象証券だけを選択
      else if (!hasPayPaySec && noETFSec > 0 && codes.length == noETFSec) {
        deleteSecFromETF();
      }
      // 上記以外
      else {
        normalMerge();
      }
    }
    return (data);
  }
  
  const undateFundCount = (obj) => {
    let qobj = $.qjfilter({data: mergeCompanyCode4ETF()});
    let filters = createFilter();
    
    qobj.clear();
    qobj.parse(filters);
    
    $(".box-control .number").text(qobj.count().toLocaleString());
    $(".box-control-head .number").text(qobj.count().toLocaleString());
    
    let n = !obj ? "" : obj.target.getAttribute("name");
    
    // キーワード
    if (n != "check_01") {
      (() => {
        let filter = $.extend({}, filters);
        qobj.clear();
        delete filter["CNDKeyword"];
        qobj.parse(filter);
        $keyword.each((idx, elm) => {
          let count = qobj.get("CNDKeyword", [$(elm).val()]);
          $(elm).next().find(".qik_count").text(`(${count})`);
          
          let $often_btn = $(`.btn-often-selected[data-id="${$(elm).attr("id")}"]`);
          $often_btn.find(".qik_count").text(`(${count})`);
        });
      })();
    }
    
    // 投資対象資産
    if (n != "check_02") {
      (() => {
        let filter = $.extend({}, filters);
        qobj.clear();
        delete filter["CNDAssets"];
        qobj.parse(filter);
        $assets.each((idx, elm) => {
          let count = qobj.get("CNDAssets", [$(elm).val()]);
          $(elm).next().find(".qik_count").text(`(${count})`);
          
          let $often_btn = $(`.btn-often-selected[data-id="${$(elm).attr("id")}"]`);
          $often_btn.find(".qik_count").text(`(${count})`);
        });
      })()
    }
    
    // 投資対象地域
    if (n != "check_03") {
      (() => {
        let filter = $.extend({}, filters);
        qobj.clear();
        delete filter["CNDRegion"];
        qobj.parse(filter);
        $region.each((idx, elm) => {
          let count = qobj.get("CNDRegion", [$(elm).val()]);
          $(elm).next().find(".qik_count").text(`(${count})`);
          
          let $often_btn = $(`.btn-often-selected[data-id="${$(elm).attr("id")}"]`);
          $often_btn.find(".qik_count").text(`(${count})`);
        });
      })()
    }
    
    // 決算頻度
    if (n != "check_04") {
      (() => {
        let filter = $.extend({}, filters);
        qobj.clear();
        delete filter["CNDFrequency"];
        qobj.parse(filter);
        $frequency.each((idx, elm) => {
          let count = qobj.get("CNDFrequency", [$(elm).val()]);
          $(elm).next().find(".qik_count").text(`(${count})`);
          
          let $often_btn = $(`.btn-often-selected[data-id="${$(elm).attr("id")}"]`);
          $often_btn.find(".qik_count").text(`(${count})`);
        });
      })()
    }
  }
  
  const createFilter = () => {
    let filters = {};
    
    // キーワード
    let tmp = [];
    $keyword.filter(":checked").each((idx, elm) => {
      tmp.push($(elm).val());
    });
    if (tmp.length > 0) {
      filters["CNDKeyword"] = tmp;
    }
    
    // 投資対象資産
    tmp = [];
    $assets.filter(":checked").each((idx, elm) => {
      tmp.push($(elm).val());
    });
    if (tmp.length > 0) {
      filters["CNDAssets"] = tmp;
    }
    
    // 投資対象地域
    tmp = [];
    $region.filter(":checked").each((idx, elm) => {
      tmp.push($(elm).val());
    });
    if (tmp.length > 0) {
      filters["CNDRegion"] = tmp;
    }
    
    // 決算頻度
    tmp = [];
    $frequency.filter(":checked").each((idx, elm) => {
      tmp.push($(elm).val());
    });
    if (tmp.length > 0) {
      filters["CNDFrequency"] = tmp;
    }
    
    // 販売会社
    tmp = [];
    $(".box-fundsearch .sales [type=checkbox]").filter(":checked").each((idx, elm) => {
      tmp.push($(elm).val());
    });
    if (tmp.length > 0) {
      filters["CompanyCode"] = tmp;
    }
    
    return (filters);
  }
  
  const getUpDownClass = (v) => {
    let result = "even";
    if (v) {
      let num = parseFloat(v);
      result = num > 0 ? "up" : num < 0 ? "down": "even";
    }
    return (result);
  }
  
  const getUpDownClass2 = (v) => {
    return (/^[+]/.test(v) ? "up" : /^[-]/.test(v) ? "down" : "even");
  }
  
  const createReferenceDate = (data) => {
    let ref_date = "----年--月--日";
    let latest = "";
    for (let i = 0; i < data.length; i++) {
      let current = data[i].ReferenceDate.replace(/[年月日]/g, "");
      if (current) {
        if (!latest) {
          latest = current;
        }
        else {
          latest = parseInt(latest) < parseInt(current) ? latest : current;
        }
      }
    }
    if (latest) {
      ref_date = `${latest.substr(0, 4)}年${latest.substr(4, 2)}月${latest.substr(6, 2)}日`;
    }
    $("#searchResult").text(`基準日：${ref_date}`);
  }
  
  const createRow = (data, row, sort_type, fav_state) => {
    let col_name = (d => {
      let url = !d.FundName || !d.DetailUrl ? `#` : d.DetailUrl;
      let fund_name = !d.FundName ? `<span class="line_short"></span>` : `<a href="${url}" data-fcode="${d.FundCode}">${d.FundName.replace(/\(R\)/gi, "\xAE")}</a>`;
      let redempt_text = d.IsRedemption ? `<p class="redemptionmerger-label">${d.RedemptionText}</p>` : ``;
      let merger_text = d.IsMerger ? `<p class="redemptionmerger-label">${d.MergerText}</p>` : ``;
      let area_label = "";
      let nisa_label = "";
      for (let cat of d.Category) {
        switch (cat) {
          case "6": area_label += '<li class="label-area">国内株式</li>'; break;
          case "7": area_label += '<li class="label-area">海外株式</li>'; break;
          case "1": area_label += '<li class="label-area">国内債券</li>'; break;
          case "2": area_label += '<li class="label-area">海外債券</li>'; break;
          case "3": area_label += '<li class="label-area">リート</li>'; break;
          case "8": area_label += '<li class="label-area">バランス・その他</li>'; break;
          case "11": area_label += '<li class="label-area">公社債投信</li>'; break;
          case "18": nisa_label += '<span class="growth"><span>NISA</span><span>成長</span></span>'; break;
          case "17": nisa_label += '<span class="accumulation"><span>NISA</span><span>つみたて</span></span>'; break;
        }
      }
      
      return ( 
        `<div class="col name">
          <p>${fund_name}</p>
          ${redempt_text}${merger_text}
          <ul class="lst-label">
            ${area_label}
            <li class="label-nisa">
              ${nisa_label}
            </li>
          </ul>
        </div>`);
    })(data);
    let col_basic = (d => {
      let nav_null = !d.NetAssetValue ? ` null` : ``;
      let nav_highlight = sort_type == "nav" ? ` highlight` : ``;
      let nav = !d.NetAssetValue ? `<span class="line_short"></span>` : `<span>${d.NetAssetValue}<span class="units">円</span></span>`;
      let cv_null = !d.ChangeValue ? ` null` : ``;
      let cv_highlight = sort_type == "chgv" ? ` highlight` : ``;
      let cv_updown = getUpDownClass(d.ChangeValue);;
      let cv = !d.ChangeValue ? `<span class="line_short"></span>` : `<span class="${cv_updown}">${d.ChangeValue}<span class="units">円</span></span>`;
      let cr_null = !d.ChangeRate ? ` null` : ``;
      let cr_highlight = sort_type == "chgr" ? ` highlight` : ``;
      let cr_updown = getUpDownClass2(d.ChangeRate);
      let cr = !d.ChangeRate ? `<span class="line_short"></span>` : `<span class="${cr_updown}">${d.ChangeRate}<span class="units">%</span></span>`;
      let tav_null = !d.TotalNetAsset ? ` null` : ``;
      let tav_highlight = sort_type == "tav" ? ` highlight` : ``;
      let tav = !d.TotalNetAsset ? `<span class="line_short"></span>` : `<span>${d.TotalNetAsset}<span class="units">億円</span></span>`;
      return (
        `<div class="col-stack basic">
          <div class="col number${nav_null}${nav_highlight}">${nav}</div>
          <div class="col number before-ratio-yen${cv_null}${cv_highlight}">${cv}</div>
          <div class="col number before-ratio-par${cr_null}${cr_highlight}">${cr}</div>
          <div class="col number total${tav_null}${tav_highlight}">${tav}</div>
        </div>`);
    })(data);
    let col_return = (d => {
      let rtnd_null = !d.ReturnDaily ? ` null` : ``;
      let rtnd_highlight = sort_type == "rtnd" ? ` highlight` : ``;
      let rtnd_updown = getUpDownClass2(d.ReturnDaily);
      let rtnd = !d.ReturnDaily ? `<span class="line_short"></span>` : `<span class="${rtnd_updown}">${d.ReturnDaily}<span class="units">%</span></span>`;
      let rtn1M_null = !d.Return1M ? ` null` : ``;
      let rtn1M_highlight = sort_type == "rtn1m" ? ` highlight` : ``;
      let rtn1M_updown = getUpDownClass2(d.Return1M);
      let rtn1M = !d.Return1M ? `<span class="line_short"></span>` : `<span class="${rtn1M_updown}">${d.Return1M}<span class="units">%</span></span>`;
      let rtn3M_null = !d.Return3M ? ` null` : ``;
      let rtn3M_highlight = sort_type == "rtn3m" ? ` highlight` : ``;
      let rtn3M_updown = getUpDownClass2(d.Return3M);
      let rtn3M = !d.Return3M ? `<span class="line_short"></span>` : `<span class="${rtn3M_updown}">${d.Return3M}<span class="units">%</span></span>`;
      let rtn6M_null = !d.Return6M ? ` null` : ``;
      let rtn6M_highlight = sort_type == "rtn6m" ? ` highlight` : ``;
      let rtn6M_updown = getUpDownClass2(d.Return6M);
      let rtn6M = !d.Return6M ? `<span class="line_short"></span>` : `<span class="${rtn6M_updown}">${d.Return6M}<span class="units">%</span></span>`;
      let rtn1Y_null = !d.Return1Y ? ` null` : ``;
      let rtn1Y_highlight = sort_type == "rtn1y" ? ` highlight` : ``;
      let rtn1Y_updown = getUpDownClass2(d.Return1Y);
      let rtn1Y = !d.Return1Y ? `<span class="line_short"></span>` : `<span class="${rtn1Y_updown}">${d.Return1Y}<span class="units">%</span></span>`;
      let rtn3Y_null = !d.Return3Y ? ` null` : ``;
      let rtn3Y_highlight = sort_type == "rtn3y" ? ` highlight` : ``;
      let rtn3Y_updown = getUpDownClass2(d.Return3Y);
      let rtn3Y = !d.Return3Y ? `<span class="line_short"></span>` : `<span class="${rtn3Y_updown}">${d.Return3Y}<span class="units">%</span></span>`;
      let rtn5Y_null = !d.Return5Y ? ` null` : ``;
      let rtn5Y_highlight = sort_type == "rtn5y" ? ` highlight` : ``;
      let rtn5Y_updown = getUpDownClass2(d.Return5Y);
      let rtn5Y = !d.Return5Y ? `<span class="line_short"></span>` : `<span class="${rtn5Y_updown}">${d.Return5Y}<span class="units">%</span></span>`;
      let rtnAll_null = !d.ReturnAll ? ` null` : ``;
      let rtnAll_highlight = sort_type == "rtnall" ? ` highlight` : ``;
      let rtnAll_updown = getUpDownClass2(d.ReturnAll);
      let rtnAll = !d.ReturnAll ? `<span class="line_short"></span>` : `<span class="${rtnAll_updown}">${d.ReturnAll}<span class="units">%</span></span>`;
      return (
        `<div class="col-stack return">
          <div class="col number daily${rtnd_null}${rtnd_highlight}">${rtnd}</div>
          <div class="col number monthly${rtn1M_null}${rtn1M_highlight}">${rtn1M}</div>
          <div class="col number${rtn3M_null}${rtn3M_highlight}">${rtn3M}</div>
          <div class="col number${rtn6M_null}${rtn6M_highlight}">${rtn6M}</div>
          <div class="col number annual${rtn1Y_null}${rtn1Y_highlight}">${rtn1Y}</div>
          <div class="col number${rtn3Y_null}${rtn3Y_highlight}">${rtn3Y}</div>
          <div class="col number${rtn5Y_null}${rtn5Y_highlight}">${rtn5Y}</div>
          <div class="col number${rtnAll_null}${rtnAll_highlight}">${rtnAll}</div>
        </div>`);
    })(data);
    let col_report = (d => {
      let url = d.HasReport ? d.ReportUrl : ``;
      let report = d.HasReport ? `<a href="${url}" class="pdf" target="_blank" data-fcode="${d.FundCode}"><span class="pc">PDF</span><span class="sp">月次レポート</span></a>` : `<span class="line_short"></span>`;
      return (`<div class="col report">${report}</div>`);
    })(data);
    let col_favorite = (d => {
      let is_fav = fav_state == true ? ' added" disabled' : '"';
      let fav = d.IsRedemption || d.IsMerger ? `<span class="line_short"></span>` : `<button type="button" class="btn-favorite${is_fav} data-code="${d.NAMCode}" data-fcode="${d.FundCode}"><span>登録<span class="pc">する</span></span><span>登録済</span></button>`
      return (`<div class="col favorite">${fav}</div>`);
    })(data);
    
    let fundcd = `00${row}`.slice(-3);
    return (`<div class="row fund" data-fundcd="${fundcd}">${col_name}${col_basic}${col_return}${col_report}${col_favorite}</div>`);
  }
  
  const createTable = () => {
    let $box_notice = $(".box-notice:not('.error')");
    let $blk_table = $(".blk-table");
    let $box_control = $(".box-control > dl");
    let $box_fundsearch = $(".box-fundsearch");
    let $box_control_anchor = $("dd ul a");
    
    const bc_observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (data.length > 0) {
          if (entry.intersectionRatio > 0) {
            if (!$box_control.hasClass("change")) {
              $box_control.removeClass("noresult").removeClass("confirm").addClass("change");
              $($box_control_anchor[0]).removeAttr("tabindex");
              $($box_control_anchor[1]).attr("tabindex", -1);
            }
          }
          else {
            if (!$box_control.hasClass("confirm")) {
              $box_control.removeClass("noresult").removeClass("change").addClass("confirm");
              $($box_control_anchor[1]).removeAttr("tabindex");
              $($box_control_anchor[0]).attr("tabindex", -1);
            }
          }
        }
        else {
          $box_control.removeClass("change").removeClass("confirm").addClass("noresult");
        }
        bc_observer.unobserve(entry.target);
      });
    }, {
      root: null,
      rootMargin: "0px",
      threshold: 1.0
    });
    
    let qobj = $.qjfilter({data: mergeCompanyCode4ETF()});
    let filters = createFilter();
    
    qobj.clear();
    qobj.parse(filters);
    let data = qobj.list();
    
    let sort_dir = $(".sort-switch.down").length > 0 ? ".down" : $(".sort-switch.up").length > 0 ? ".up" : "";
    let sort_type = $(`.sort-switch${sort_dir}`).attr("data-sort");
    let dir = sort_dir == ".down" ? -1 : 1;
    let getSortData = (type, data) => {
      return (type == "name" ? data.FundNameKana :
        type == "nav" ? data.SRTNetAssetValue :
        type == "chgv" ? data.SRTChangeValue :
        type == "chgr" ? data.SRTChangeRate :
        type == "tav" ? data.SRTTotalNetAsset :
        type == "rtnd" ? data.SRTReturnDaily :
        type == "rtn1m" ? data.SRTReturn1M :
        type == "rtn3m" ? data.SRTReturn3M :
        type == "rtn6m" ? data.SRTReturn6M :
        type == "rtn1y" ? data.SRTReturn1Y :
        type == "rtn3y" ? data.SRTReturn3Y :
        type == "rtn5y" ? data.SRTReturn5Y :
        type == "rtnall" ? data.SRTReturnAll :
        data.FundNameKana);
    };
    let null_data = data.filter(e => getSortData(sort_type, e) == null);
    let not_null_data = data.filter(e => getSortData(sort_type, e) != null);
    not_null_data.sort((a, b) => {
      const a_val = getSortData(sort_type, a);
      const b_val = getSortData(sort_type, b);
      let result = 0;
      if (sort_type == "name") {
        result = ((a_val > b_val ? 1 : a_val < b_val ? -1 : 0) * dir);
      }
      else {
        result = ((a_val - b_val) * dir);
      }
      return (result);
    });
    data = not_null_data.concat(null_data);

    $box_notice.hide();
    $blk_table.hide();
    $(".tbl-fundsearch .row.fund").remove();
    if (data.length == 0) {
      $box_notice.show();
    }
    else {
      let output = "";
      for (let i = 0; i < data.length; i++) {
        output += createRow(data[i], i, sort_type, fav_list.includes(data[i].NAMCode));
      }
      $(".tbl-fundsearch").append(output);
      createReferenceDate(data);
      $.fn.fn_addFavoriteEvent();
      document.querySelectorAll('.btn-favorite:not(.added)').forEach((elm) => {
        elm.addEventListener('click', (e) => {
          sendLog(4, $(e.currentTarget).attr("data-fcode"));
        }, false)
      });
      $blk_table.show();
    }
    bc_observer.observe($box_fundsearch[0]);
  }
  
  const createSalesCompanyList = (data) => {
    let buff = "";
    if (data.status == 0 && data.hitcount > 0) {
      let arr = data.data || [];
      for (let i = 0; i < arr.length; i++) {
        let type = arr[i].CompanyType == "1" ? "securities" :
                  arr[i].CompanyType == "2" ? "banks" :
                  arr[i].CompanyType == "3" ? "insurance" :
                  arr[i].CompanyType == "4" ? "shortTerm" : 
                  arr[i].CompanyType == "5" ? "banks" : "";
        buff += `<input type="checkbox" name="${type}" id="${type}_${arr[i].CompanyCode}" value="${arr[i].CompanyCode}" data-text="${arr[i].CompanyName}" data-kana="${arr[i].CompanyNameKana}" tabindex="-1">`;
      }
      $('.box-fundsearch .sales > dd').prepend(buff);
    }
  }
  
  const createSalesCompanyTable = (data) => {
    if (data.status == 0 && data.hitcount > 0) {
      let arr = data.data || [];
      let patterns = [
        /^[アイウエオ].*$/,
        /^[カキクケコガギグゲゴ].*$/,
        /^[サシスセソザジズゼゾ].*$/,
        /^[タチツテトダヂヅデド].*$/,
        /^[ナニヌネノ].*$/,
        /^[ハヒフヘホバビブベボパピプペポ].*$/,
        /^[マミムメモ].*$/,
        /^[ヤユヨ].*$/,
        /^[ラリルレロ].*$/,
        /^[ワヲン].*$/
      ];
      let alpha_pattern = /^[a-zA-Zａ-ｚＡ-Ｚ].*$/;
      let buff = "";
      
      // 証券会社
      for (let i = 0; i < patterns.length; i++) {
        buff = "";
        for (let d of arr.filter(d => d.CompanyType == "1" && alpha_pattern.test(d.CompanyName) == false).filter(d => patterns[i].test(d.CompanyNameKana))) {
          buff += `<li><button type="button" class="btn-checkbox" data-id="securities_${d.CompanyCode}">${d.CompanyName}</button></li>`;
        }
        $(`#securities .modal-contents:nth-child(1) .blk-search-company > details:nth-child(${i + 2}) ul`).append(buff);
      }
      buff = "";
      for (let d of arr.filter(d => d.CompanyType == "1" && alpha_pattern.test(d.CompanyName))) {
        buff += `<li><button type="button" class="btn-checkbox" data-id="securities_${d.CompanyCode}">${d.CompanyName}</button></li>`;
      }
      $(`#securities .modal-contents:nth-child(1) .blk-search-company > details:last-child ul`).append(buff);
      buff = "";
      
      // 銀行
      for (let i = 0; i < patterns.length; i++) {
        buff = "";
        for (let d of arr.filter(d => (d.CompanyType == "2" || d.CompanyType == "5") && alpha_pattern.test(d.CompanyName) == false).filter(d => patterns[i].test(d.CompanyNameKana))) {
          buff += `<li><button type="button" class="btn-checkbox" data-id="banks_${d.CompanyCode}">${d.CompanyName}</button></li>`;
        }
        $(`#banksetc .modal-contents:nth-child(1) .blk-search-company:nth-child(1) > details:nth-child(${i + 2}) ul`).append(buff);
      }
      buff = "";
      for (let d of arr.filter(d => (d.CompanyType == "2" || d.CompanyType == "5") && alpha_pattern.test(d.CompanyName))) {
        buff += `<li><button type="button" class="btn-checkbox" data-id="banks_${d.CompanyCode}">${d.CompanyName}</button></li>`;
      }
      $(`#banksetc .modal-contents:nth-child(1) .blk-search-company:nth-child(1) > details:last-child ul`).append(buff);
      
      // 保険会社
      buff = "";
      for (let d of arr.filter(d => d.CompanyType == "3")) {
        buff += `<li><button type="button" class="btn-checkbox" data-id="insurance_${d.CompanyCode}">${d.CompanyName}</button></li>`;
      }
      $(`#banksetc .modal-contents:nth-child(1) .blk-search-company:nth-child(2) > details:nth-child(1) ul`).append(buff);
      
      // 短資会社
      buff = "";
      for (let d of arr.filter(d => d.CompanyType == "4")) {
        buff += `<li><button type="button" class="btn-checkbox" data-id="shortTerm_${d.CompanyCode}">${d.CompanyName}</button></li>`;
      }
      $(`#banksetc .modal-contents:nth-child(1) .blk-search-company:nth-child(2) > details:nth-child(2) ul`).append(buff);
    }
  }
  
  const createRecentCheckbox = (e) => {
    let buff = "";
    for (let modal_type of ["securities", "banksetc"]) {
      buff = "";
      const $modal = $(`#${modal_type} .modal-contents:nth-child(1) .blk-search-company > details.recent ul`);
      const type = modal_type == "securities" ? modal_type : "banks";
      $modal.empty().removeAttr("open");
      for (let d of select_companies[type].slice(-5)) {
        let $company = $(`.box-fundsearch .sales #${type}_${d}`);
        if ($company.length > 0) {
          buff += `<li><button type="button" class="btn-checkbox recent" data-id="${type}_${d}">${$company.attr("data-text")}</button></li>`;
        }
      }
      if (buff) {
        $modal.append(buff);
      }
    }
  }
  
  const addCompnayCheckboxEvent = () => {
    $.fn.fn_setSalesCompany();
    $("[data-search-sales] .btn-checkbox").off("click").on("click", (e) => {
      $.fn.fn_searchSalesCheckAction(e);
      let $company = $(`.box-fundsearch .sales #${$(e.currentTarget).attr("data-id")}`);
      if ($(e.currentTarget).hasClass("is-checked")) {
        let idx = -1;
        if ($company.attr("name") == "securities") {
          idx = select_companies.securities.indexOf($company.val());
          if (idx != -1) {
            select_companies.securities.splice(idx, 1);
          }
          select_companies.securities.push($company.val());
        }
        else if ($company.attr("name") == "banks") {
          idx = select_companies.banks.indexOf($company.val());
          if (idx != -1) {
            select_companies.banks.splice(idx, 1);
          }
          select_companies.banks.push($company.val());
        }
      }
    });
    $("[data-search-sales] .btn-check-remove").off("click").on("click", (e) => {
      if (e.currentTarget.disabled) {
        return;
      }
      $.fn.fn_modalCheckAllRemove();
    });
  }
  
  const initCompanyCheckbox = () => {
    $(`#securities .modal-contents:nth-child(1) .blk-search-company > details`).not(".recent").removeAttr("open");
    $(`#banksetc .modal-contents:nth-child(1) .blk-search-company > details`).not(".recent").removeAttr("open");
    
    $.fn.fn_modalCheckAllRemove();
    let p = new URLSearchParams(location.search);
    for (let code of p.get("company") ? p.get("company").split(",") : []) {
      const $checkbox = $(`.box-fundsearch .sales [type='checkbox'][value=${code}]`);
      let type = $checkbox.attr("name");
      if (type != "securities") {
        type = "banksetc";
      }
      const org_modal_type = $.fn.setOpenSalesGroup(type);
      const $btn = $(`#${type}[data-search-sales] .btn-checkbox[data-id="${$checkbox.attr("id")}"]`);
      $btn.not(".recent").click();
      $.fn.setOpenSalesGroup(org_modal_type);
      $btn.closest("details").removeAttr("open").attr("open", true);
    }
  }
    
  const initOftenSelectedButton = (data) => {
    if (data.status == 0 && data.hitcount > 0) {
      let arr = data.data || [];
      let id_array = arr[0].FundName ? arr[0].FundName.split(",") : [];

      // よく選択される条件ボタンの表示
      $('.btn-list-often-selected > li').hide();
      for (let i = id_array.length - 1; i >= 0; i--) {
        let $btn = $(`.btn-often-selected[data-log-id=${id_array[i]}]`);
        if ($btn.length > 0) {
          let $btn_parent = $btn.parent();
          $btn_parent.prependTo($('.btn-list-often-selected'));
          $btn_parent.css({"display": "flex"});
        }
      }
    }
  }
  
  $(() => {
    fav_list = jQuery.fn.fn_getFavoriteList();
    
    select_companies = readRecentlyViewCompany();
    
    let p = new URLSearchParams(location.search);
    
    $(".btn-group span.icon").show();
    
    dispLoading();
    $.when(getCompanyInfo(), getProductClassInfo(), getOftenSelectedInfo()).done((r1, r2, r3) => {
      if (r1[0].status != 0 ||
          r1[0].section1.status != 0 ||
          r2[0].status != 0 ||
          r2[0].section0.status != 0 ||
          r2[0].section1.status != 0 ||
          r3[0].status != 0 ||
          r3[0].section1.status != 0){
        ajaxError();
        removeLoading();
      }
      else {
        createSalesCompanyList(r1[0].section1);
        createSalesCompanyTable(r1[0].section1);
        createRecentCheckbox();
        addCompnayCheckboxEvent();
        initCompanyCheckbox();
        $.fn.fn_setSalesSelectData();
        initOftenSelectedButton(r3[0].section1);
        initFreeword(p, r2[0].section1);
        initCheckbox(p);
        initTab(p);
        initSort(p);
        getFundInfo($("#qik_freeword").val(), $("#qik_freeword").val(), true, r1[0].section1);
      }
    }).fail((x, s, e) => {
      ajaxError();
      removeLoading();
    }).always((r, s, e) => {
    });
    
    // ファンド名テキストボックスからフォーカスアウト
    $("#qik_freeword").on("blur", (e) => {
      const $target = $(e.currentTarget);
      $target.val($target.val().trim());
    });
    
    // ファンド名テキストボックス入力
    $("#qik_freeword").on("input", (e) => {
      const $target = $(e.currentTarget);
      if ($target.val() != "") {
        $(".text-error").hide();
      }
    });
    
    // ファンド名検索ボタン押下
    $(".form-fundsearch form").submit(() => {
      $("#qik_freeword").val($("#qik_freeword").val().trim());
      freeword = $("#qik_freeword").val();
      $('.box-fundsearch .btn-toggle [type="checkbox"]').prop("checked", false);
      $('.blk-conditions.has_checked').removeClass("has_checked");
      $('.blk-conditions.is-open').removeClass("is-open");
      $.fn.fn_salesCheckAllRemove();
      getFundInfo(freeword, freeword)
      .done((r, s, x) => {
        if (freeword != "") {
          scrollSearchResult();
        }
      });
      updateUrl();
      $nisa_label.removeClass("has_nisa-label");
      $(".btn-often-selected").removeClass("is-selected");
      
      if (freeword != "") {
        $(".text-error").hide();
      }
      else {
        $(".text-error").show();
      }
      
      return (false);
    });

    // 条件を組み合わせて検索トグルボタン押下（販売会社除く）
    $(document).on("click", `${btn_tgl} [type='checkbox']`, (e) => {
      freeword = $("#qik_freeword").val();
      let p = new URLSearchParams(location.search);
      let text = p.get("text") || "";
      if (freeword != text) {
        getFundInfo(freeword, freeword);
      }
      updateUrl();
      undateFundCount(e);
      createTable();

      // よく選択される条件ボタンの選択
      let $often_btn = $(`.btn-often-selected[data-id="${$(e.currentTarget).attr('id')}"]`);
      if ($($often_btn).hasClass("is-selected")) {
        $($often_btn).removeClass("is-selected");
      }
      else {
        $($often_btn).addClass("is-selected");
      }
    });
    
    // 検索条件をクリアボタン押下
    $(document).on("click", `.btn-search-clear`, (e) => {
      if (freeword) {
        getFundInfo("", "");
        updateUrl();
        undateFundCount();
        freeword = "";
      }
      else {
        updateUrl();
        undateFundCount(e);
        createTable();
      }
      $nisa_label.removeClass("has_nisa-label");
      $(".btn-often-selected").removeClass("is-selected");
      $(".text-error").hide();
      if ($(".box-accordion-fundsearch").hasClass("is-open")) {
        $(".btn-accordion-fundsearch").click();
      }
    });
    
    // 一覧切り替えタブ押下
    $(document).on("click", "input#tab_02-01, input#tab_02-02", (e) => {
      updateUrl();
    });
    
    // ソートボタン押下
    $(document).on("click", ".sort button", (e) => {
      updateUrl();
      createTable();
    });
    
    let tmp_select_companies = {securities: [], banks: []};
    
    // 証券会社/銀行などボタン押下
    $(document).on("click", "button[data-modal]", (e) => {
      tmp_select_companies = structuredClone(select_companies);
      createRecentCheckbox();
      addCompnayCheckboxEvent();
      initCompanyCheckbox();
    });
    
    // 証券会社/銀行などモーダルダイアログ確定ボタン押下
    document.querySelectorAll('.btn-modal-confirm').forEach(element => {
      element.addEventListener('click', (e) => {
        freeword = $("#qik_freeword").val();
        let p = new URLSearchParams(location.search);
        let text = p.get("text") || "";
        if (freeword != text) {
            getFundInfo(freeword, freeword);
        }
        updateUrl();
        undateFundCount(e);
        createTable();
        writeRecentlyViewCompany();
      }, false);
    });
    
    // 証券会社/銀行などモーダルダイアログ閉じるボタン押下
    document.querySelectorAll('.btn-modal-close').forEach(element => {
      element.addEventListener('click', (e) => {
        select_companies = structuredClone(tmp_select_companies);
      }, false);
    });
    
    // 証券会社/銀行などモーダルダイアログオーバーレイ押下
    document.querySelectorAll('.modal-fundsearch').forEach(element => {
      element.addEventListener('click', (e) => {
        select_companies = structuredClone(tmp_select_companies);
      }, false);
    });
    
    // 選択した販売会社削除ボタン押下
    $(document).on("click", ".lst-selected dt button", (e) => {
      $.fn.fn_salesCheckAllRemove();
      freeword = $("#qik_freeword").val();
      let p = new URLSearchParams(location.search);
      let text = p.get("text") || "";
      if (freeword != text) {
        getFundInfo(freeword, freeword);
      }
      updateUrl();
      undateFundCount(e);
      createTable();
    });
    
    // ログ集計用検索条件の取得
    const getCond4Log = () => {
      let keywords = [];
      let assets = [];
      let regions = [];
      let frequencies = [];
      $(`[type='checkbox']:checked`).each((idx, elm) => {
        let name = $(elm).attr("name");
        switch (name) {
          case "check_01":
            keywords.push(`1${$(elm).val()}`);
            break;
            
          case "check_02":
            assets.push(`2${$(elm).val()}`);
            break;
            
          case "check_03":
            regions.push(`3${$(elm).val()}`);
            break;
            
          case "check_04":
            const v = $(elm).val();
            frequencies.push(
              v == "1" ? "41" :
              v == "2" ? "42" :
              v == "3" ? "43" :
              v == "4" ? "44" :
              "45");
            break;
        }
      });
      
      let result = [];
      if (keywords.length > 0) {
        result.push(...keywords);
      }
      if (assets.length > 0) {
        result.push(...assets);
      }
      if (regions.length > 0) {
        result.push(...regions);
      }
      if (frequencies.length > 0) {
        
        result.push(...frequencies);
      }
      
      let freeword = encodeURIComponent($("#qik_freeword").val());
      
      let selectedList = jQuery.fn.fn_getSalesSelectedList();
      let companyNameList = [];
      selectedList.forEach((c_id) => {
        let obj = $(`#${c_id}`);
        companyNameList.push({
          name: obj.attr('data-text'),
          kana: obj.attr('data-kana')
        });
      });
      companyNameList.sort((x, y) => {
        return (x.kana > y.kana ? 1 : x.kana < y.kana ? -1 : 0);
      });
      let companies = '';
      let count = companyNameList.length > 10 ? 10 : companyNameList.length;
      for (let i = 0; i < count; i++) {
        if (companies != '') {
          companies += ' ';
        }
        companies += companyNameList[i].name;
      }
      companies = encodeURIComponent(companies);
      
      return (`${freeword},${companies},${result.length > 0 ? result.join(",") : ""}`);
    };
    
    // 検索結果を見るボタン押下
    $(document).on("click", ".btn-search-confirm", (e) => {
      sendLog(1, getCond4Log());
      $(".text-error").hide();
    });
    
    // ファンド名リンク押下
    $(document).on("click", ".tbl-fundsearch .col.name a", (e) => {
      let fcode = $(e.currentTarget).attr("data-fcode");
      let cond = getCond4Log();
      sendLog(2, `${fcode}${cond ? "," : ""}${cond}`);
    });
    
    // 月次レポートリンク押下
    $(document).on("click", ".tbl-fundsearch .col.report a", (e) => {
      sendLog(3, $(e.currentTarget).attr("data-fcode"));
    });
    
    // NISA成長投資枠、NISAつみたて投資枠ボタン押下
    $(document).on("click", "#check_01-01, #check_01-02", (e) => {
      $nisa_label.removeClass("has_nisa-label");
      if ($nisag.prop("checked") == true || $nisat.prop("checked") == true) {
        $nisa_label.addClass("has_nisa-label");
      }
    });
    
    // よく選択される条件で検索ボタン押下
    $(document).on("click", ".btn-often-selected", (e) => {
      let $target = $(`#${$(e.currentTarget).attr("data-id")}`); 
      $target.click();
      
      let $target_block = $target.closest(".blk-conditions");
      if ($target_block.length > 0) {
        if ($target_block.hasClass("has_checked")) {
          $($target_block).addClass("is-open");
        }
        else {
          $($target_block).removeClass("is-open");
        }
      }
    });
  });
})();
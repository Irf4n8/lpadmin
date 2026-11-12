/*
   Licensed to the Apache Software Foundation (ASF) under one or more
   contributor license agreements.  See the NOTICE file distributed with
   this work for additional information regarding copyright ownership.
   The ASF licenses this file to You under the Apache License, Version 2.0
   (the "License"); you may not use this file except in compliance with
   the License.  You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
*/
var showControllersOnly = false;
var seriesFilter = "";
var filtersOnlySampleSeries = true;

/*
 * Add header in statistics table to group metrics by category
 * format
 *
 */
function summaryTableHeader(header) {
    var newRow = header.insertRow(-1);
    newRow.className = "tablesorter-no-sort";
    var cell = document.createElement('th');
    cell.setAttribute("data-sorter", false);
    cell.colSpan = 1;
    cell.innerHTML = "Requests";
    newRow.appendChild(cell);

    cell = document.createElement('th');
    cell.setAttribute("data-sorter", false);
    cell.colSpan = 3;
    cell.innerHTML = "Executions";
    newRow.appendChild(cell);

    cell = document.createElement('th');
    cell.setAttribute("data-sorter", false);
    cell.colSpan = 7;
    cell.innerHTML = "Response Times (ms)";
    newRow.appendChild(cell);

    cell = document.createElement('th');
    cell.setAttribute("data-sorter", false);
    cell.colSpan = 1;
    cell.innerHTML = "Throughput";
    newRow.appendChild(cell);

    cell = document.createElement('th');
    cell.setAttribute("data-sorter", false);
    cell.colSpan = 2;
    cell.innerHTML = "Network (KB/sec)";
    newRow.appendChild(cell);
}

/*
 * Populates the table identified by id parameter with the specified data and
 * format
 *
 */
function createTable(table, info, formatter, defaultSorts, seriesIndex, headerCreator) {
    var tableRef = table[0];

    // Create header and populate it with data.titles array
    var header = tableRef.createTHead();

    // Call callback is available
    if(headerCreator) {
        headerCreator(header);
    }

    var newRow = header.insertRow(-1);
    for (var index = 0; index < info.titles.length; index++) {
        var cell = document.createElement('th');
        cell.innerHTML = info.titles[index];
        newRow.appendChild(cell);
    }

    var tBody;

    // Create overall body if defined
    if(info.overall){
        tBody = document.createElement('tbody');
        tBody.className = "tablesorter-no-sort";
        tableRef.appendChild(tBody);
        var newRow = tBody.insertRow(-1);
        var data = info.overall.data;
        for(var index=0;index < data.length; index++){
            var cell = newRow.insertCell(-1);
            cell.innerHTML = formatter ? formatter(index, data[index]): data[index];
        }
    }

    // Create regular body
    tBody = document.createElement('tbody');
    tableRef.appendChild(tBody);

    var regexp;
    if(seriesFilter) {
        regexp = new RegExp(seriesFilter, 'i');
    }
    // Populate body with data.items array
    for(var index=0; index < info.items.length; index++){
        var item = info.items[index];
        if((!regexp || filtersOnlySampleSeries && !info.supportsControllersDiscrimination || regexp.test(item.data[seriesIndex]))
                &&
                (!showControllersOnly || !info.supportsControllersDiscrimination || item.isController)){
            if(item.data.length > 0) {
                var newRow = tBody.insertRow(-1);
                for(var col=0; col < item.data.length; col++){
                    var cell = newRow.insertCell(-1);
                    cell.innerHTML = formatter ? formatter(col, item.data[col]) : item.data[col];
                }
            }
        }
    }

    // Add support of columns sort
    table.tablesorter({sortList : defaultSorts});
}

$(document).ready(function() {

    // Customize table sorter default options
    $.extend( $.tablesorter.defaults, {
        theme: 'blue',
        cssInfoBlock: "tablesorter-no-sort",
        widthFixed: true,
        widgets: ['zebra']
    });

    var data = {"OkPercent": 100.0, "KoPercent": 0.0};
    var dataset = [
        {
            "label" : "FAIL",
            "data" : data.KoPercent,
            "color" : "#FF6347"
        },
        {
            "label" : "PASS",
            "data" : data.OkPercent,
            "color" : "#9ACD32"
        }];
    $.plot($("#flot-requests-summary"), dataset, {
        series : {
            pie : {
                show : true,
                radius : 1,
                label : {
                    show : true,
                    radius : 3 / 4,
                    formatter : function(label, series) {
                        return '<div style="font-size:8pt;text-align:center;padding:2px;color:white;">'
                            + label
                            + '<br/>'
                            + Math.round10(series.percent, -2)
                            + '%</div>';
                    },
                    background : {
                        opacity : 0.5,
                        color : '#000'
                    }
                }
            }
        },
        legend : {
            show : true
        }
    });

    // Creates APDEX table
    createTable($("#apdexTable"), {"supportsControllersDiscrimination": true, "overall": {"data": [0.984375, 500, 1500, "Total"], "isController": false}, "titles": ["Apdex", "T (Toleration threshold)", "F (Frustration threshold)", "Label"], "items": [{"data": [1.0, 500, 1500, "GET /v1/oms/_licence"], "isController": false}, {"data": [1.0, 500, 1500, "GET /v1/oms/paper/positions"], "isController": false}, {"data": [1.0, 500, 1500, "GET /v1/oms/_instances"], "isController": false}, {"data": [0.75, 500, 1500, "POST /v1/oms/_auth/login"], "isController": false}, {"data": [1.0, 500, 1500, "GET /v1/oms/paper/all_open"], "isController": false}, {"data": [1.0, 500, 1500, "GET /v1/oms/_auth/me"], "isController": false}, {"data": [1.0, 500, 1500, "GET /v1/oms/paper/mam/masters"], "isController": false}, {"data": [1.0, 500, 1500, "GET /v1/oms/paper/health"], "isController": false}, {"data": [1.0, 500, 1500, "GET /v1/oms/paper/orders"], "isController": false}, {"data": [1.0, 500, 1500, "GET /v1/oms/paper/history"], "isController": false}]}, function(index, item){
        switch(index){
            case 0:
                item = item.toFixed(3);
                break;
            case 1:
            case 2:
                item = formatDuration(item);
                break;
        }
        return item;
    }, [[0, 0]], 3);

    // Create statistics table
    createTable($("#statisticsTable"), {"supportsControllersDiscrimination": true, "overall": {"data": ["Total", 32, 0, 0.0, 87.71875000000001, 37, 510, 54.0, 177.99999999999994, 456.6999999999998, 510.0, 20.11313639220616, 465.4784235543683, 4.846598051539912], "isController": false}, "titles": ["Label", "#Samples", "FAIL", "Error %", "Average", "Min", "Max", "Median", "90th pct", "95th pct", "99th pct", "Transactions/s", "Received", "Sent"], "items": [{"data": ["GET /v1/oms/_licence", 6, 0, 0.0, 41.66666666666667, 39, 45, 41.0, 45.0, 45.0, 45.0, 5.361930294906166, 5.272913873994638, 1.1257959115281502], "isController": false}, {"data": ["GET /v1/oms/paper/positions", 2, 0, 0.0, 54.5, 42, 67, 54.5, 67.0, 67.0, 67.0, 2.8449502133712663, 4.946712748933144, 0.7723595305832148], "isController": false}, {"data": ["GET /v1/oms/_instances", 6, 0, 0.0, 127.5, 42, 428, 69.0, 428.0, 428.0, 428.0, 3.9787798408488064, 4.750704575596817, 0.843159399867374], "isController": false}, {"data": ["POST /v1/oms/_auth/login", 2, 0, 0.0, 357.5, 205, 510, 357.5, 510.0, 510.0, 510.0, 1.7436791630340018, 2.25622547951177, 0.5755503487358326], "isController": false}, {"data": ["GET /v1/oms/paper/all_open", 2, 0, 0.0, 81.0, 80, 82, 81.0, 82.0, 82.0, 82.0, 2.785515320334262, 194.1808844011142, 0.7535036559888579], "isController": false}, {"data": ["GET /v1/oms/_auth/me", 2, 0, 0.0, 49.5, 37, 62, 49.5, 62.0, 62.0, 62.0, 2.962962962962963, 2.8385416666666665, 0.7841435185185185], "isController": false}, {"data": ["GET /v1/oms/paper/mam/masters", 2, 0, 0.0, 52.0, 51, 53, 52.0, 53.0, 53.0, 53.0, 2.7548209366391188, 7.22871470385675, 0.753271349862259], "isController": false}, {"data": ["GET /v1/oms/paper/health", 6, 0, 0.0, 50.5, 37, 67, 50.5, 67.0, 67.0, 67.0, 5.371530886302597, 5.618075760966875, 1.1487942032229186], "isController": false}, {"data": ["GET /v1/oms/paper/orders", 2, 0, 0.0, 94.5, 89, 100, 94.5, 100.0, 100.0, 100.0, 2.628120893561104, 529.94877217477, 0.705794185282523], "isController": false}, {"data": ["GET /v1/oms/paper/history", 2, 0, 0.0, 55.5, 53, 58, 55.5, 58.0, 58.0, 58.0, 2.7247956403269753, 225.19611077997277, 0.7344175749318801], "isController": false}]}, function(index, item){
        switch(index){
            // Errors pct
            case 3:
                item = item.toFixed(2) + '%';
                break;
            // Mean
            case 4:
            // Mean
            case 7:
            // Median
            case 8:
            // Percentile 1
            case 9:
            // Percentile 2
            case 10:
            // Percentile 3
            case 11:
            // Throughput
            case 12:
            // Kbytes/s
            case 13:
            // Sent Kbytes/s
                item = item.toFixed(2);
                break;
        }
        return item;
    }, [[0, 0]], 0, summaryTableHeader);

    // Create error table
    createTable($("#errorsTable"), {"supportsControllersDiscrimination": false, "titles": ["Type of error", "Number of errors", "% in errors", "% in all samples"], "items": []}, function(index, item){
        switch(index){
            case 2:
            case 3:
                item = item.toFixed(2) + '%';
                break;
        }
        return item;
    }, [[1, 1]]);

        // Create top5 errors by sampler
    createTable($("#top5ErrorsBySamplerTable"), {"supportsControllersDiscrimination": false, "overall": {"data": ["Total", 32, 0, "", "", "", "", "", "", "", "", "", ""], "isController": false}, "titles": ["Sample", "#Samples", "#Errors", "Error", "#Errors", "Error", "#Errors", "Error", "#Errors", "Error", "#Errors", "Error", "#Errors"], "items": [{"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}]}, function(index, item){
        return item;
    }, [[0, 0]], 0);

});
